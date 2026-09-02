# 🤝 세션 인수인계 — 2026-09-02 오후 (A↔B 재검 루프 5라운드 + KG 구조 검증 3라운드 + 팀원 전부 merge·배포)

> 작업 구간: **9/2 10:00 ~ 18:00** (이 PC 신규 세팅 → 재검 루프 → 팀 merge → 배포). 앞 문서는 `docs/HANDOFF_2026-09-02.md`(새벽, 펀드 채점 루프 완주).
> 이 문서는 **무엇이 배포돼 있고, 루프가 어떻게 돌고, 다음(6라운드)에 뭘 하는지**만 담는다. 채점 상세는 라운드 보고서(§3 파일표)가 정본.
>
> 🔴 **D-4** — 제출 마감 9/6 23:59. 제안서 PDF(40점)는 아직 미착수. §6 참조.

---

## 0. 지금 상태

| 항목 | 상태 |
| :-- | :-- |
| main = 서버 | **`8db421b`** (push · 코드+DB 전체 배포 완료, 서버 DB md5 `ba88e7b6…` 로컬 일치) |
| 기준선 | pytest **325** · gold **147/147** · dupkeys 0 · 6R 동결선 snapshot 64 통과 |
| 이 구간 커밋 | 리드 세션 73개 (fix 30+ · docs/eval 30+ · merge 6) + 팀원 merge 전부 |
| 팀원 | 채권(seohynun) main 직접 push 전부 반영 · ETF(LEEbyeoungchul) `eda/domestic_etfs` 17커밋 main 에 merge · 데이터(jeonghyeon) 8/25 이후 변화 없음. **원격 5개 브랜치 전부 main 미합류 0** |
| 미커밋 | 없음 (`eval/probe_recheck_2026-09-02_r6.json` 6건 부분 실측은 삭제 — 6R 은 처음부터) |
| 서버 | `/health` ok · agent_ready true · planner hcx · 테스트 API 키(과금 0, 분당 60요청/6만 토큰) |

### 이 PC 환경 (HANDOFF 새벽판 §2 절차를 이 PC 에 적용한 결과)
- `python` 은 WindowsApps 스텁이라 실행 실패 → **`./.venv/Scripts/python.exe`**(3.11.9) 또는 `py -3.11`. 스크립트 앞에 `export PYTHONIOENCODING=utf-8`.
- 로컬 전용(gitignore): `1.금융상품/`(주최 xlsx) · `data/`(DB·external 4.3GB) · `secrets/`(deploy_key·pem). 원본 zip 은 `C:\Users\NT751\Downloads\data`.
- `.env` 는 example 복사본 — HCX 키 없음. **로컬 HCX 경로 실행 불가**, 결정층(라우터·Ground·가드·조립기)만 pytest 로 검증. HCX 실측은 서버 `/answer` 로.
- git remote 는 `https://Song-exp@github.com/...` 로 사용자명 고정(huhjihye 계정은 쓰기 권한 없음). 부모 폴더 `toxin_2026` 도 별도 레포 — pj 를 거기 커밋하지 않는다.
- SSH(배포)는 ACG 통과 확인됨(공인 IP 210.183.172.228).

### 🔴 다른 PC 에서 이어가기 (pull 하면 바로 이어갈 수 있다 — 조건 3개)

| # | 할 것 | 왜 |
| :-: | :-- | :-- |
| 1 | `git pull` | 코드·yaml·문서·eval·테스트 전부 git 에 있다 |
| 2 | `pip install -r requirements-dev.txt` | **`ruamel.yaml` 추가됨** — `scripts/check_yaml_dupkeys.py`(기준선 3종 중 하나) 의존. 없으면 스크립트가 sys.exit |
| 3 | `python scripts/build_ontology.py` | 🔴 **필수** — 오늘 KG 스키마가 바뀌었다(kg_alias `match_kind`·kg_node 라벨 슬롯·Country/FundAttribute 노드·`provenance=label_conflict`). pull 만으로는 DB 가 새 코드와 안 맞아 Ground·게이트 테스트가 깨진다 |
| 4 | 기준선 3종 확인 | pytest **325** · gold **147/147** · dupkeys 0 (+ `tests/test_snapshot_round6.py` 동결선 64) |

- gitignore 라 git 으로 안 오는 것: 마스터 DB `data/financial_products.db`(263MB, 8/22 불변) · `1.금융상품/`(주최 xlsx) · `secrets/`(deploy_key·pem) · `.env`. 그 PC 에 없으면 드라이브 공유 또는 `C:\Users\NT751\Downloads\data` 의 zip 3개(`data.zip`·`1.금융상품_(2).zip`·`secrets.zip`)를 레포 루트에 풀면 된다.
- **오늘 새로 수집한 외부 데이터는 없다** — `data/external` 변경 0, git 에 데이터·코드북 추가 0. KG 는 커밋된 `ontology/shared/*.yaml`·`ontology/codebooks/*.csv`·`scripts/build_ontology.py` 에서 전부 재생성된다(재빌드 결정성 확인: 같은 입력 → kg_* 행 집합 동일).
- 서버는 이미 최신(8db421b, 코드+DB) — **배포 없이 §6 P1 의 6R 실측부터 시작**하면 된다.

---

## 1. 루프 구조 (사용자 설계)

```
[B 심사관]  공모펀드 도메인 전문가 — docs/domain/public_funds.md 가 판단 근거 최우선
            서버 원본(answer·trace·context 전문) 읽기 + DB gold 직접 실측 → 판정 · 층 분해 · 일반 규칙 수정안 · 형제 질문
     │  보고서 docs/recheck_2026-09-02_roundN.md · verdicts json
     ▼
[A 수리]    수정안을 결정층(가드·게이트·조립기·KG 빌더)에 일반 규칙으로 구현 · 회귀 테스트 · 항목 단위 커밋
     │  push·배포 금지 (오케스트레이터가)
     ▼
[오케스트레이터]  기준선 → 팀원 merge → push → 재빌드+전체 배포 → probe 실측 → B 재채점 → 대조 md 갱신
```

🔴 **사용자 원칙 (전 에이전트 지시문 고정)**: 문항별 예외 금지 — 전체 온톨로지 그림(ttl → shared yaml → enums → kg_* → 가드 체인) 안에서 **질의 부류 단위 일반 규칙**으로. 이름 하드코딩 0 · 같은 목적 가드 중복 0 · KG/ttl 변경은 build_ontology + gold + pytest 로 4도메인 영향 증명, 커밋 본문에 "일반 규칙 / 영향 범위".

### 도구
| 파일 | 용도 |
| :-- | :-- |
| `eval/probe_server.py` | 서버 `/answer` 순차 실측 → JSON. `ID<TAB>질문` 파일 입력(세 번째 칸부터 무시). **`--resume`** 으로 10분 제한 이어 돌리기 |
| `eval/render_probe_md.py` | 라운드별 JSON + verdicts → 문항별 **초기/수정 후 답변 전문 대조 md** |
| `eval/verdicts_2026-09-02.json` · `eval/verdicts_kg_2026-09-02.json` | 라운드별 판정 요지 (B 가 갱신) |
| `tests/test_snapshot_round6.py` + `tests/snapshots/round6_fixedline.json` | **동결선** — ✅ 64문항의 결정층(라우팅·Ground·가드 후 SQL·조립기) 스냅샷. 수리가 기존 ✅ 를 깨면 로컬에서 잡힌다 |
| `eval/kg_structure_questions.jsonl` | KG 구조 검증 35문항 gold (`questions_*` glob 밖 — gold check 규격과 다름) |

---

## 2. 라운드별 결과 (전부 서버 실측)

### 2-1. 재검 계열 (HANDOFF 새벽판 §1 P1 7문항 → 형제로 확장)

| 라운드 | 배포 커밋 | 문항 | 판정 | 요지 |
| :-- | :-- | :-- | :-- | :-- |
| 1R | 9e0b691 (배포 전) | 7 | ✅0 🟡6 ❌1 | 값은 대체로 맞고 서술·집계 결함. R7 클래스 도배 |
| 2R | 31e72ef | 19 | 개선 9 · **회귀 R2**(yaml COALESCE 비한정→모호컬럼 기각) · S11 | P1~P7 + 리뷰 ②-1~7 |
| 3R | e56767d | 33 | ✅16 ✅값/🟡6 🟡3 ❌8 · 회귀 0 | Q1~Q7 + 채권 팀원 가드. ❌ 전부 조립기 앞단(이름 등호·KG 접두 절단 라벨) |
| 4R | 6bad723 | 49 | ✅21 ✅값/🟡19 🟡3 ❌6 · **회귀 5** | KG 구조 큐 S1·S3~S6 + 부류 A~D. 회귀 = 새 Country 노드가 상품명 안 국가어를 잡음 |
| 5R | 1e0e641 | 61 | **✅33 ✅값/🟡20 ❌8** · 회수 10 · 회귀 4 | 부류 I~M + N1·N2·N4. 회귀 = 규칙 간 간섭(오타 라우터 키↔고유명 후보 · 템플릿↔윈도 함수 · 0행 결정) |

### 2-2. KG 구조 검증 (온톨로지·KG 를 시험하는 35문항, 7축)

| 라운드 | 배포 커밋 | 문항 | 판정 | 요지 |
| :-- | :-- | :-- | :-- | :-- |
| 기준선 | 31e72ef | 35 | ✅5 🟡7 ❌23 | 거짓 0개 3 · 좌수 환각 · ETF alias 오적용 · 구조적 약점 17건 |
| 2R | 6bad723 | 35 | ✅17 🟡6 ❌12 | 감점 위험 4/5 닫힘. S1·S3~S6 실물 정합 · 4도메인 부작용 0 |
| 3R | 1e0e641 | 35+X25 | KG ✅17 🟡4 ❌14 · X ✅8 ❌17 | **회귀 3**(FundAttribute 라벨 'ETF'·'아시아' 가 Region/AssetClass 명사와 충돌). 환각 4건이 오거절로 이동 |

### 2-3. 6R 수리분 (배포됐으나 **미실측** — 8db421b)
A 가 프리즈 전 필수 11항 중 **10항 구현**(F5 교차 분기 기계 조립만 보류). 구현 전 간섭 지도(`docs/recheck_2026-09-02_round6_plan.md`) + 동결선 스냅샷 먼저 커밋. 항목: N 오타 키 고유명 후보 제외 · F1 라벨 충돌 노드 빌더 검증 제외(KG 재빌드) · F2 클래스 종속 값 단일 MAX 금지 · I′+J′ 경계 원문 기준·이름 토큰 사후조건 · F4 0행 문구 세 갈래 · O 숫자 절 폐기 재실행 · P 템플릿 단순 술어·윈도 함수 기각 · F3 구성종목 JOIN 템플릿 · F6 기본모수 단독 절 판정.

---

## 3. 파일 지도

| 파일 | 내용 |
| :-- | :-- |
| `docs/recheck_2026-09-02_round1.md` … `round5.md` | 재검 라운드별 B 판정·층 분해·수정안·형제 질문 |
| `docs/recheck_2026-09-02_round1_review.md` | 배포 전 코드 리뷰(조건부 승인, 펀드키 규약 결함 판정) |
| `docs/recheck_2026-09-02_round6_plan.md` | 6R 간섭 지도 11항 |
| `docs/recheck_loop_2026-09-02.md` | **61문항 × 5라운드 답변 전문 대조** (사용자 요청 산출물) |
| `docs/kg_structure_probe_design_2026-09-02.md` | KG 35문항 설계·구조적 약점 17 |
| `docs/kg_structure_probe_round1~3_2026-09-02.md` | KG 라운드별 판정·구조 큐·런타임 큐 |
| `docs/kg_structure_loop_2026-09-02.md` | KG 60문항 × 3라운드 답변 전문 대조 |
| `eval/probe_recheck_2026-09-02*.json` | 서버 원본 응답 전부 (r1~r5, r4/r5 는 recheck·kg 분리본 포함) |
| `docs/DEPLOY.md` §0-C-1 | **동시 작업 기간 배포 규칙** (§4) |

---

## 4. 🔴 배포 규칙 (2026-09-02 리드 결정 — `docs/DEPLOY.md` §0-C-1 · `deploy.sh` 헤더)

- 배포는 기본 **재빌드 + 전체 모드**: `python scripts/build_ontology.py` → `bash deploy/deploy.sh`.
- `--code-only`/`--yaml-only` 는 아래가 **비어 있을 때만**:
  ```bash
  git diff --name-only <직전 배포 커밋>..HEAD -- ontology/shared ontology/codebooks ontology/*.ttl scripts/build_ontology.py scripts/build_db.py scripts/gen_*.py
  ```
- 팀원 pull 뒤 `build_ontology.py` 필수. "내 수리 반영 안 됐다" → `git log <서버 배포 커밋>..main` 부터.
- DB 동일성은 md5 가 아니라 kg_* 행 집합 EXCEPT 대조.
- 배포 출력은 grep/tail 로 줄이지 말 것(새벽판 §0-18). 항상 `PYTHONIOENCODING=utf-8` + venv PATH 앞.

---

## 5. 리드 판정 대기 안건 (루프가 건드리지 않고 남긴 것)

1. **펀드 순자산 축** — 목록 경로 `MAX`(대표 클래스) vs 개별 조회 `SUM`(클래스 합). 같은 펀드 순자산이 문항마다 다름(KB중국본토A주 1,453 vs 3,345억). 도메인 문서 §4.8 기준 SUM 이 맞으나 gold_sql 이 바뀜. 현재 목록 머리줄에 "대표 클래스 기준" 고지만.
2. **펀드키 규약** — 현행 `(or_co, mtco)` 3,040펀드 vs 대표예탁원번호 `rptt` 1,809. 우리 235→88·iM 205→29 등 운용사 순위가 키 산물. 표시 단위로만 rptt 접기 적용 중. gold·테스트·주최 규약 얽혀 키 자체는 불변.
3. **S2 역할 분리** — 운용사·수탁사·판매사를 `fp:Organization` 하위 역할 클래스 + `ref_organization` 참조 테이블로. build_db 스키마 변경이라 팀 조율.
4. **도메인 문서 정정 큐** — `public_funds.md` §3.1(순자산 클래스 동일)·§3.4(mtco = 모펀드 키)·§1.3(기준가 없음 — `bns_bpr` 스냅샷은 실재) 가 2차 데이터와 어긋남.

---

## 6. 🔴 다음 순서

**P0 — 제안서 PDF (40점, 미착수)**. 이 루프가 §02 소재를 만들었다: 층별 분해(집행층 실패가 지배적 → 결정층 기계 조립), "모델은 복사만 하게 하라" 원칙 3종, 온톨로지 확장(라벨 슬롯·국가/속성 노드·ABSENT 전수·등급 범위 선언)이 4도메인 부작용 0 으로 들어간 실측, 팀원의 채권·ETF 온톨로지 전수 재검증. `docs/proposal/README.md` 목차 01·03~06 미작성.

**P1 — 6라운드 (프리즈 전 마지막 수리 확인)** — 서버는 이미 8db421b 라 배포 불필요. 그대로 실측만:
1. 실측 (162문항, 10분 제한이라 3회 이어 돌리기):
   ```bash
   export PYTHONIOENCODING=utf-8
   ./.venv/Scripts/python.exe eval/probe_server.py eval/probe_recheck_2026-09-02_r6.txt -o eval/probe_recheck_2026-09-02_r6.json --resume
   ```
   (재검 61 R·S·T·V·W + 5R 형제 Y16 + KG 35 + X25 + KG3R 형제 Z25)
2. JSON 을 recheck(R/S/T/V/W/Y) · kg(KG/X/Z) 로 분리 → B 두 명 병렬 채점. 지시문 요지: `docs/domain/public_funds.md` 최우선 · 이전 ✅ 전수 회귀 확인 · 표본 5건 원문 대조 §⑥ · 수렴 판정(프리즈 전 필수 vs 이월) · 형제 질문은 `ID<TAB>질문` 뒤에 주석 두지 말 것(5R X 사고). 산출물 `docs/recheck_2026-09-02_round6.md` · `docs/kg_structure_probe_round4_2026-09-02.md` + verdicts 갱신 → `render_probe_md.py` 로 대조 md 재생성.
3. 판정 기준: 5R ✅33 + KG ✅17 이 유지되고 6R 수리 대상(R7·S1·S2·V5·W2·W3·W6·KG-023·005·012·X25·028·X1·X2)이 닫히면 **펀드 도메인 코드 프리즈** → 7R 은 수리 없이 같은 질문 2회 실행(비결정 확인)만.
4. 회귀가 나오면 6R 계획서의 간섭 지도로 원인 층을 먼저 짚고, **동결선 스냅샷을 깨는 수리는 하지 않는다**.

**P2 — 이월 큐** (프리즈 후 또는 예선 뒤): F5 교차 분기 기계 조립(N3+S7+R4) · G-1/G-2 랭킹 템플릿·클래스 열거 · E 클래스수 · H 문구 · B-3 · B-4 범위 · Q · S1-b 3자 브랜드 슬롯 · N5~N8 · R6·R8/R9/R14 · N10 · S9 · §5 안건 4건.

---

## 7. 이 구간의 교훈

1. **수리 묶음이 크면 규칙끼리 간섭한다** — 4R(Country 노드↔상품명 국가어)·5R(token canon↔Region 라벨, 오타 라우터 키↔고유명 후보)의 회귀는 전부 새 규칙 둘의 교집합에서 났다. 6R 부터 "간섭 지도 선행 + 동결선 스냅샷" 을 절차로 박았다.
2. **B 채점은 원문 대조로 검증 가능하다** — 라운드마다 표본 3~5건을 오케스트레이터가 원본 answer·DB 값과 재대조했고 전부 일치. B 지시문에 §⑥ 표본 인용을 넣어 이 검증을 상시화.
3. **팀원 커밋이 KG 입력을 건드리기 시작하면 배포 판단을 사람에게 맡기지 않는다** — §4 규칙의 배경.
4. **probe 입력 형식 사고** — B 보고서의 `ID<TAB>질문<TAB>(주석)` 줄을 그대로 쓰면 주석까지 질의된다(5R X25 재실측). 러너는 두 칸만 읽게 고쳤고, B 에게는 주석을 아래 목록으로 분리하게 했다.
