# 온톨로지 기반 금융상품 질의응답 에이전트 — 팀 트리플에이치

자연어 질문을 국내 채권·국내/해외 ETF·공모펀드 마스터에 대한 SQL 조회로 옮겨 답한다.
온톨로지 선언과 지식 그래프가 조회 대상과 조건을 확정하고, 결정층 가드가 그 조건을 SQL 에 강제한다.

**데이터 기준일 2026-08-24** (영업일 2026-08-22 · 해외 2026-08-23)

---

## 평가용 API

| 항목 | 값 |
| :-- | :-- |
| **엔드포인트** | **`https://49.50.134.229.nip.io/answer`** |
| 메서드 | `GET /answer?question_id=<문항ID>&question=<URL 인코딩한 질문>` |
| 프로토콜 | HTTPS(Let's Encrypt) · **HTTP 80 도 같은 경로로 직접 응답** |
| 인증 | 없음 |
| 상태 확인 | `https://49.50.134.229.nip.io/health` |

응답은 항상 **HTTP 200 + 5필드 JSON**이며 모든 값이 문자열이다. 답할 수 없는 질의도 같은 형식으로 돌려준다.

```bash
curl -sG "https://49.50.134.229.nip.io/answer" \
  --data-urlencode "question_id=Q1" \
  --data-urlencode "question=국고채는 총 몇 종목이야?"
```

```json
{
  "question_id": "Q1",
  "question": "국고채는 총 몇 종목이야?",
  "retrieved_context": "조회 결과 원문(컬럼 헤더 + 행)",
  "think_trace": "1. [Normalize] … 2. [Intent] … 3. [Route] … 4. [Ground] … 5. [Gate] …",
  "answer": "국고채는 총 295종목입니다 (기준일 2026-08-24)."
}
```

전체 규격·예시·오류 처리는 [`docs/API_SPEC.md`](docs/API_SPEC.md).

---

## 실행 환경

Python 3.12 · SQLite · FastAPI. 외부 LLM 은 HyperCLOVA X(HCX-005) 하나만 쓴다.

### 1. 환경 변수

```bash
cp .env.example .env
# HYPERCLOVA_API_KEY = CLOVA Studio 에서 발급한 Bearer 토큰
# SITE_ADDRESS       = <공인 IP>.nip.io  (Caddy 가 이 이름으로 인증서를 받는다)
# AGENT_READY        = 1
```

### 2. 데이터베이스 만들기

`data/financial_products.db` 는 저장소에 없다(원본 데이터는 push 하지 않는다). 아래 순서로 만든다.

```bash
python scripts/build_db.py              # 주최 제공 엑셀 4종 → 마스터 4테이블
python scripts/load_external_holdings.py # 외부 수집분 → ext_* 4테이블
python scripts/build_ontology.py        # yaml·shared → kg_node/alias/edge/closure + ttl 5분할
```

- **주최 제공 데이터**: `1.금융상품/` 아래에 `prbd01n001_data.xlsx` · `_schema.xlsx` 형식으로 둔다.
- **외부 수집 데이터**: 용량 문제로 저장소에 넣지 않고 **별도 전달**한다. 수집 방법은 `scripts/fetch_*.py`,
  출처·수집일·라이선스는 [`data/external/holdings/SOURCES.md`](data/external/holdings/SOURCES.md) 에 있다.
  수집분 없이도 서버는 뜨지만 구성종목 교차질의(예: "삼성전자를 담은 ETF")는 답하지 못한다.

### 3. 서버 실행

```bash
docker compose up -d --build          # Caddy(80/443) → api(8000)
curl -s http://localhost/health
```

컨테이너 없이 돌릴 때는 아래와 같다.

```bash
pip install -r requirements.txt
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### 4. 회귀 테스트

```bash
pytest -q            # 1,610건 — DB 가 있어야 하는 항목은 없으면 자동 skip
```

---

## 저장소 구조

| 경로 | 내용 |
| :-- | :-- |
| `src/runtime/` | 라우팅 · KG 접지 · 게이트 · 결정층 가드 · 답변 조립 |
| `src/hcx/` | HyperCLOVA X 연동 — 의도 분석 · SQL 계획 · 답변 작성 |
| `src/api/` | FastAPI 서버(`/answer` · `/health`) |
| `ontology/enums/` | 도메인별 규칙 yaml — 조건식·모수·되묻기·부재 선언의 단일 원천 |
| `ontology/shared/` | 개체·별칭·계층 선언 |
| `ontology/*.ttl` | 위에서 생성한 온톨로지 5분할(공통·채권·국내ETF·해외ETF·펀드) |
| `scripts/` | 데이터 수집 · DB 빌드 · 온톨로지 빌드 |
| `eval/` | 평가 문항(`.jsonl`)과 실행기 |
| `tests/` | 회귀 테스트 |
| `deploy/` | Caddy 설정과 배포 스크립트 |

---

## 질의 처리 흐름

```
질문 → 의도 분석(HCX) → 온톨로지 탐색·SQL 추출 → 답변 생성 → 5필드 JSON
                          ├ 규칙 필터링: 상품군 판정 · 부재 선언 · 값 표준표 · 기준일 · 되묻기
                          └ KG 접지 → 근거문서 → SQL 계획(HCX) → 확정식·가드 → 검사 → 실행
```

- 선언만으로 판정되는 질의(없는 속성·없는 등급·기준일 밖·다의어)는 SQL 을 만들지 않고 즉답한다.
- 개수·분포·랭킹·목록은 조회 결과를 코드가 그대로 옮긴다(작성 단계 LLM 호출 없음).
- 조회 결과가 0행이면 조건을 완화하지 않고 "확인할 수 없음"으로 답한다.
