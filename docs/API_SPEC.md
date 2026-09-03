# API 명세 — `GET /answer` (제출 항목 3 · 제안서 부록 D)

> 원본 규격: 주최 「평가용 API End-point 제출 안내」(`PROJECT.md` §7). 구현: `src/api/main.py`(FastAPI) · 배포: `deploy/`(Caddy 80/443 → api:8000, `DEPLOY.md`).
> 이 파일은 README 옆에 두는 **제출용 명세**다. 규격과 구현이 다르면 구현을 고친다 — 이 파일을 구현에 맞추지 않는다.
> 1차 2026-09-03 (채권 담당). ▶ 리드 확인: 최종 엔드포인트 URL.

## 1. 엔드포인트

| 항목 | 값 |
| :-- | :-- |
| Base URL | `https://49.50.134.229.nip.io` (▶ 리드 확인 — `07_리드_공통절.md` §0.2 기준. HTTP 80 도 열려 있음) |
| 질의 | `GET /answer?question_id=<id>&question=<urlencoded 질문>` — 경로 고정 |
| 상태 확인 | `GET /health` → `{"status":"ok","agent_ready":true,"planner":"hcx","version":"<app.version>"}` |
| 인증 | 없음(주최 발신 IP 허용 방식). POST 바디 없음. 미정의 파라미터는 무시 |
| 호출 방식 | 순차 1건씩(동시 요청 없음) · 타임아웃/5xx 시 주최가 최대 2회 재시도 |
| 응답 시간 | 권장 60초 이내 · 하드 300초 · 내부 목표 15초(r15 중앙값 3.2초) |

## 2. 요청

```bash
curl -sG "https://49.50.134.229.nip.io/answer" \
  --data-urlencode "question_id=Q-001" \
  --data-urlencode "question=현재 판매 가능한 원화채권 중 AA- 이상 종목 알려줘"
```

| 파라미터 | 타입 | 필수 | 설명 |
| :-- | :-- | :-: | :-- |
| `question_id` | string | ✓ | 주최 문항 ID. 응답에 그대로 되돌린다 |
| `question` | string | ✓ | 자연어 질의(URL 인코딩). Single-turn — 되묻기 답변도 이 한 번의 응답이 최종이다 |

## 3. 응답 — 5필드 전부 `string`, 항상 HTTP 200 + `application/json; charset=utf-8`

| 필드 | 내용 | 생성 주체 |
| :-- | :-- | :-- |
| `question_id` | 요청값 그대로 | — |
| `question` | 요청값 그대로 | — |
| `retrieved_context` | 실행한 SQL 의 **조회 결과 원문**(파이프 구분 표, 컬럼 헤더 포함). 답변의 근거. 0행이면 빈 문자열 | DB |
| `think_trace` | 파이프라인 단계 로그 `N. [단계] 내용` — Normalize · Route · Ground · Gate · Plan · Guard · Execute · Answer/Decision. **LLM 생성물이 아니라 실행 로그**다. 실행한 SQL 전문이 `[Plan] SQL 생성` 줄 아래 실린다 | 런타임 |
| `answer` | 사용자 답변. 목록·집계·거절은 규칙으로 기계 조립, 서술형만 HCX 가 쓴다 | 규칙 / HCX |

### 3.1 답변 가능 예 (2026-09-03 서버 실측 · 2.4초)

```json
{
  "question_id": "OFFICIAL-001",
  "question": "현재 판매 가능한 원화채권 중 AA- 이상 종목 알려줘",
  "retrieved_context": "pd_no | pd_nm | crd_grd\nKR380805AG24 | 한국수출입금융 2602차-할인-181 | AAA\nKR310210GC85 | 산업금융채권 22신이0400-0824-1 | AAA\n…(30행)",
  "think_trace": "1. [Normalize] 질의 정규화 — 길이 30\n2. [Route] 상품군 — domestic_bonds · 근거: 머리명사 채권 · 값 ['AA-']\n3. [Ground] KG 개체 매핑 — 'AA-' → CG_AAm (CreditGrade) → domestic_bonds.crd_grd='AA-' / '원화' → Curr_KRW (Currency) → domestic_bonds.curr_cd='KRW'\n4. [Gate] 통과 — 대상 테이블 ['domestic_bonds']\n5. [Plan] 근거문서 조립 — …\n6. [Guard] 등급 서열 확장 — …\n7. [Plan] SQL 생성 — 아래 문장을 실행합니다\nSELECT DISTINCT pd_no, pd_nm, crd_grd FROM domestic_bonds WHERE TRIM(crd_grd) IN ('AAA', 'AA+', 'AA0', 'AA-') AND curr_cd = 'KRW' AND mat_dt >= 20260824 LIMIT 30\n8. [Guard] SQL 검사 통과 (…)\n9. [Execute] 30행 조회 (상한 30)\n10. [Answer] 채권 목록 답변 기계 조립 — …, HCX 0회",
  "answer": "조건에 해당하는 채권은 전체 15,792종목이며, 그중 30개는 다음과 같습니다 (기준일 2026-08-24).\n\n1. 한국수출입금융 2602차-할인-181 — 신용등급 AAA\n2. 산업금융채권 22신이0400-0824-1 — 신용등급 AAA\n…"
}
```

### 3.2 답변 불가 예 — 존재하지 않는 등급 (게이트 기각 · HCX 0회 · 0.3초)

```json
{
  "question_id": "OFFICIAL-NA-001",
  "question": "신용등급 AAAA인 채권 찾아줘",
  "retrieved_context": "",
  "think_trace": "1. [Normalize] 질의 정규화 — 길이 17\n2. [Route] 상품군 — domestic_bonds · 근거: 머리명사 채권\n3. [Ground] KG 개체 매핑 — 'AAA' → CG_AAA (CreditGrade) → domestic_bonds.crd_grd='AAA'\n4. [Gate] 기각 — 'AAAA' 는 신용등급 표준표(20종)에 없음 — 존재하지 않는 등급\n5. [Decision] HCX 호출 없이 종료 (근거는 Gate 단계)",
  "answer": "'AAAA'는 존재하지 않는 신용등급이라 확인할 수 없습니다. 유효 등급은 AAA~C 체계입니다."
}
```

### 3.3 되묻기 예 — 정확일치 0건, 유사 후보 제시 (2.1초)

`question=KODEX AI로봇 ETF 정보 알려줘` → `answer`: "요청하신 상품은 제공된 데이터에 없습니다. 혹시 다음 상품을 말씀하신 건가요? — KODEX AI반도체TOP2플러스 / KODEX AI전력핵심설비 / KODEX 미국AI전력핵심인프라 / KODEX 로봇액티브". 부분일치(`KODEX`·`AI`)로 엉뚱한 종목을 반환하지 않는다. 역질문은 유효 답변(주최 8/25 확인).

## 4. 오류 처리

| 상황 | 응답 | 근거 |
| :-- | :-- | :-- |
| 데이터에 근거 없음(정상 판정) | 200 + 5필드, `answer` 에 사유, `think_trace` 에 `[Gate] 기각`/`[Refuse]`/`[Decision]` | 답변불가 정답 경로 |
| 파라미터 누락·형식 오류 | 200 + 5필드(빈 `retrieved_context`, `think_trace`="1. [Error] 요청 파라미터 오류 — 답변 불가로 처리") | 재시도해도 같은 결과 |
| 런타임 오류 | 1회 자동 재실행(`0. [Retry]`) 후에도 실패면 200 + `[Error] 런타임 오류(재시도 1회 포함) — 답변 보류` | `main.py run_pipeline` |
| 그 밖의 예외 | 200 + `[Error] 내부 처리 오류` (`_fallback`) | ⚠ `PROJECT.md` §7 [!CAUTION] — 일시적 오류를 500 으로 돌려 주최 재시도 2회를 받을지는 리드 안건 A-7 |

## 5. 데이터·기준일 규약 (답변 문구와 일치)

- 마스터 4테이블 v2_20260824 · 주최 as-of 2026-08-22 · **판정·표기 기준일 2026-08-24**(구매가능 = 만기 미경과 `mat_dt >= 20260824`, 리드 결정 09-02).
- 외부 수집(ETF·펀드 구성종목, 펀드 페이지)은 `ext_*` 테이블에 태그 병기, 마스터 값은 고치지 않는다. 해외 구성종목은 `report_date` 병기.
- 0·결측은 주최 공지대로 "의도된 값" — 없으면 "미수록" 으로 답하고 유추하지 않는다.

## 6. 로컬 재현

```bash
docker compose up -d --build          # api:8000 + Caddy
curl -s localhost/health
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe eval/probe_server.py eval/probe_gold_2026-09-03_g1.txt -o /tmp/g1.json   # 서버 프로브
./.venv/Scripts/python.exe eval/run_gold_check.py                                                                           # 로컬 gold 155
```
