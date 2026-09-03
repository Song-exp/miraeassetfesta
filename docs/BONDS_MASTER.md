# 📘 국내채권 작업 전체 — 한 문서로 보기 (v3 · 2026-09-03 갱신 / 초판 08-26 · 08-27 쉬운 말 · 08-30 2차 DB)

> **이 문서가 하는 일** — 국내채권(`domestic_bonds`) 작업을 08-10 첫 EDA 부터 09-03 까지 **무엇을 만들었고, 무엇이 바뀌었고, 지금 무엇이 정본(최종)인지** 한 장으로 잇는 **지도**다. 자세한 내용은 각 문서로 링크한다. **새로운 사실은 여기에 쓰지 않는다** — 여기는 지도이고, 사실은 원래 문서에 있다.
>
> **급하면 §8 과 §10 부터 읽어라.** §8 은 "결국 어느 파일·어느 함수가 최종인가"(코드·산출물 인벤토리), §10 은 "결국 뭐가 확정됐고, 뭐는 되묻고, 뭐는 답을 못 하나"(행동 기준 결론)다.
>
> ⚠️ **데이터가 두 판이다 — 가장 먼저 알아야 할 것.** 1차: 기준일 2026-07-11 · 42,394행 × 40컬럼 / **2차: 기준일 2026-08-22 · 21,882행 × 58컬럼**. 주최가 1차를 폐기했고 08-25 부터 `main`·로컬 DB·yaml 전부 2차다. 08-26 이전 문서의 숫자는 1차일 수 있다 — §0·§3 참고. **판정·답변 표기 기준일은 2026-08-24**(리드 결정 09-02; 주최 as-of 8/22 는 데이터 설명에만, 스냅샷 산출일은 8/21).
>
> 🔴 v3 에서 바뀐 것: §2 타임라인 08-27~09-03 · §5 규칙 40종 · §6 2차 재검증 완료 표시 · §7 문서 지도에 9월 문서 · **§8 신설(최종 코드·산출물 인벤토리)** · §10 결론 갱신 · §11 남은 일.

---

## 용어 먼저 — 이 문서에 자주 나오는 말

| 용어 | 뜻 (이 문서에서 쓰는 의미) |
| :-- | :-- |
| **EDA** | 탐색적 데이터 분석. 데이터를 처음 받아서 "뭐가 들어 있고, 어디가 이상한가"를 훑는 작업 |
| **yaml** (`ontology/enums/domestic_bonds.yaml`) | 우리가 내린 판정·규칙을 적어 둔 **정본 파일**. 챗봇이 쿼리를 만들 때 이 파일의 규칙을 따르고, 빌드가 여기서 ttl·KG 를 만든다 |
| **3층** | 온톨로지가 런타임에 존재하는 세 형태 — ① 값 사전(KG 4테이블) ② 규칙 문서(yaml → 프롬프트) ③ 게이트·가드(생성 전 기각 · 생성 후 검사·교정). `docs/기술제안서/08_설계철학.md` |
| **가드(guard)** | HCX 가 만든 SQL 을 실행 전에 기계로 고치거나 기각하는 함수. 규칙을 "실었는데 무시된" 사고가 반복될 때 결정층으로 승격한 것 |
| **PK (기본키)** | 한 행을 유일하게 구분하는 열쇠. 2차는 네 컬럼(`pd_no + pd_exg_mkt + info_base_dt + info_seq`)을 합쳐야 한 행 — 그래서 `COUNT(*)` 는 종목 수가 아니다 |
| **LOT** | 2차에서 "당사가 파는 조건 한 묶음". 같은 종목이라도 시장·기준일·판매순번이 다르면 다른 LOT(=다른 행) |
| **듀레이션** | 금리가 움직일 때 채권 가격이 얼마나 흔들리는지의 척도(년). 길수록 금리에 민감 · **잔존만기** 기준일부터 만기까지 남은 기간 |
| **위장결측 · 센티넬** | 값이 있어 보이지만 "없음"을 뜻하는 값(`0`·`99`·복사값). 센티넬은 그중 특정 숫자로 표시한 것 |
| **특수구조** | 콜·풋·전환·후순위·영구 같은 조건이 붙은 채권. 08-30 부터 추천에서 **빼지 않고 표시**한다(`구조표시`) |
| **콜·풋·CB·EB·BW·FRN·코코본드·AT1·분리채권** | 발행사 조기상환권 · 투자자 조기매도권 · 전환사채 · 교환사채 · 신주인수권부사채 · 변동금리채 · 조건부자본증권 · 그중 최후순위 신종자본증권(영구채) · 국고채 원리금 분리(STRIPS) |
| **유동화(ABS·MBS)** | 대출·매출채권을 묶어 만든 채권. 발행자가 SPC 라 이름으로 위험을 판단하면 안 됨 |
| **역질문 (`clarify`)** | 질문이 여러 뜻으로 읽힐 때 되묻는 것. 주최 8/25 확인: **되묻기도 유효 답변**. Single-turn 이라 되묻기가 곧 최종 응답 |
| **결정층** | 프롬프트 규칙만으로 재현이 안 되는 되묻기·교정을 코드가 HCX 호출 전/후에 강제하는 자리(`risk_ambiguity_clarify`·`expand_grade_comparison` 등) |
| **코드북** | "이 값은 이 뜻" 대조표. 채권의 핵심은 `credit_grade_scale.csv`(신용등급 서열, 한국기업평가) |
| **정본** | 숫자가 서로 다를 때 믿는 출처. 제안서 수치는 `docs/proposal/NUMBERS.md`(생성기) 하나 |

---

## 0. 정본 우선순위 — 숫자가 서로 다르면 이 순서로 믿는다

| 순위 | 무엇 | 어디 | 판 |
| :-: | :-- | :-- | :-- |
| 1 | **라이브 DB 실측** | `data/financial_products.db` (v2_20260824 · 로컬 = 배포본 = 주최 원본, 08-30 해시 대조) | 2차 |
| 2 | **제안서 수치 생성기** | `scripts/gen_proposal_numbers.py` → [`proposal/NUMBERS.md`](proposal/NUMBERS.md) §1 "국내채권 기본모수·등급·판정 컬럼"(09-03 편입) | 2차 |
| 3 | **2차 yaml** (판정·규칙 정본) | `ontology/enums/domestic_bonds.yaml` — 숫자 주장은 `scripts/audit_bonds_rules.py` 가 DB 로 재현(112건 중 110 일치, 불일치 2 = 동의어 BW 건) | 2차 |
| 4 | 2차 재검증 문서 | [`review_2026-08-26/채권_전수조사_2026-08-30.md`](review_2026-08-26/채권_전수조사_2026-08-30.md) · [`review_2026-09-02/온톨로지_yaml_전수재검증_2026-09-02.md`](review_2026-09-02/온톨로지_yaml_전수재검증_2026-09-02.md) · [`DATA_V2_2026-08-24_impact.md`](DATA_V2_2026-08-24_impact.md) | 2차 |
| 5 | 1차 yaml · 구조도 · EDA 노트 · 검토 답글 | 커밋 `420f1cf` yaml · `domain/domestic_bonds_graph.md` · `eda/domestic_bonds_notes.md` · `review_reply_bonds_2026-08-21.md` · `additional_bonds.md` | 1차 |
| 6 | 도메인 가이드 | `domain/domestic_bonds.md` | 개념 설명이라 판과 무관 |

> 낡은 숫자를 발견하면 그 문서를 고치지 말고 "→ 정본 X" 표시만 남긴다. 09-02 전수 재검증(`f0fe676`)이 yaml·문서의 1차 잔재 200여 곳을 2차로 정정했고, 09-03 에 제안서 템플릿의 1차 수치(결측 41.1%)를 다시 잡았다 — 같은 실수가 반복되므로 **숫자는 NUMBERS 생성기에서만 가져온다.**

---

## 1. 지금 상태 — 한눈에 (1차 vs 2차, 2026-09-03 실측)

| | 1차 (7/11) | **2차 (8/22 · 판정일 8/24)** |
| :-- | --: | --: |
| 행 수 | 42,394 (행 = 종목) | **21,882** (행 = 종목 × 시장 × 기준일 × 판매LOT) |
| 종목 수 (`pd_no` distinct) | 42,394 | **20,497** (1,078종목이 2~4행) |
| 컬럼 수 | 40 (대문자) | **58** (소문자) |
| 장내 / 장외 | 24,749 / 17,645 | 17,746 / **4,136** |
| 구매가능 (`curr_cd='KRW' AND mat_dt >= 20260824`) | 매수가능 254 | **21,814행 / 20,431종목** (`buyable_quantity` 는 주최 공지로 무효 · 당사 판매조건은 634 LOT) |
| 신용등급 결측 | 41.1% | **4,020행 / 18.4%** = 국공채 2,840(미부여) + 특수채 254 + 회사채 926(미수록) · 표기 15종 |
| 위험등급 | 0~6 정수 | `'11'~'16'` + `'00'`(해당없음 19행) · 6등급 8,929행(40.8%) · 범위 **0~6** 선언 |
| 발행사 (`pd_pbcm` TRIM distinct) | 8,018 | **1,818** (KG Organization 노드 1,817) |
| 할인채 / 영구채 | 이름 파싱 | **689행** (`bd_intp_tcd`) / **266행·237종목** (`신종\|영구`) |
| `query_rules` / `clarify` / `answer_rules` | 16 / 10 / — | **40 / 다의어 6 + 사람의_선택 4 + 조건부 1 / 20** |
| ABSENT / gate_constants | — | **4 (AssetClass·Index·Region·CreditGradeHistory) / 1 (curr_cd=KRW, 09-03)** |
| 평가셋 | 1문항(OFFICIAL-001) | **36문항** + 안전 최상급 프로브 10 + 공식·불가 3 |
| 채권 전용 가드·조립기 | 0 | **약 35개 함수** (§8-3) |

**한 줄로** — 1차에서 종목명을 정규식으로 긁던 것이 2차엔 전용 컬럼으로 왔고(좋아짐), 대신 행이 종목이 아니게 됐다(복합 PK). 8/30~9/3 나흘은 **"규칙은 실렸는데 HCX 가 무시한다"** 는 사고를 하나씩 결정층 가드로 옮긴 기간이다 — 채권 오답 58건 기록이 그 이력이다(§7).

---

## 2. 타임라인 — 무엇을 언제 했나

| 날짜 | 커밋 | 무엇을 했나 | 산출물 |
| :-- | :-- | :-- | :-- |
| 08-10 | `3db171a` | **첫 EDA** — 도메인 가이드 + EDA 노트 초안 | `domain/domestic_bonds.md` · `eda/domestic_bonds_notes.md` |
| 08-12 | `37ee6aa` | 심화 — 듀레이션 값 충돌 · 분류 계층 교차 · 채권 상태 4분할 | 노트 §D.1·§D.13 |
| 08-13 | `6ca28c3` | **구조도** + 40컬럼 실제 예시 | `domain/domestic_bonds_graph.md` · `_sample.md` |
| 08-16~17 | — | 할인채 수수께끼 · 위장결측 · 사각지대 · **역질문 설계 §I** | 노트 |
| 08-18 | `74a4b87` `7a8bd8c` | **yaml 신설** + 판정 감사 | `enums/domestic_bonds.yaml` · `eda/domestic_bonds_audit_2026-08-18.md` |
| 08-20 | `bbfdf1e` | 외부 코드북 수집(담보·업종·**등급 서열**·세금·용어·발행기관) | `data/external/lookups/` |
| 08-21 | `12d27ef`~`fd22b19` | 검토 B1~B9 전건 — 기준일·영구채·듀레이션0=콜·유동화·역질문 기본값 | `review_reply_bonds_2026-08-21.md` |
| 08-22~23 | `afb4c53` | 추가 검토 — 규칙 실행성(8종 중 3종만 SQL)·외부 대조·자체 재검증 260항목 | `additional_bonds.md` |
| 08-24~25 | `3a19130` `b36bf0f` `e773737` | **2차 데이터 전환** — yaml 전면 재작성 · 재검증 8건 | `DATA_V2_2026-08-24_impact.md` · `review_recheck_2026-08-25.md` |
| 08-25 | — | **KG 노드화** — CreditGrade 표준표 21노드·2밴드(`shared/credit_grade.yaml`) · RiskGrade alias `'11'~'16'` | `ontology/shared/*.yaml` |
| 08-26~27 | `fbfd457` | 담보·업종 외부 대조 · 위험등급 방향 확정 · **검토 17건 판정 기입**(대표행 병기·외화채없음·공모사모판정·듀레이션정상) · 이 문서 초판 | `review_2026-08-26/채권_검토기록_2026-08-27.md` |
| 08-29 | 회의 | 수익률 728% 유동화 후순위 → **고위험제외**(1등급·C0·사모) + 6% 주의 문구 결정 | `meeting_2026-08-29.md` |
| 08-30 | `ad3449d` `cdf09f6` `faa8bb2` `3bd381f` `3552356` | **전수조사 🔴6·🟡7·🟢10** — NULL-안전 고위험제외 · 게이트 사후검사 · 특수구조제외→구조표시 · 위험등급방향·등급서열 · Ground fallback 제거 · `router.route()` · clarify·answer_rules 프롬프트 경로 · 규칙 압축 · **평가셋 24문항** · 토큰 상한 1536 | `채권_전수조사_2026-08-30.md` · `채권_규칙_원문_2026-08-30.md` · `채권_재점검_2026-08-30_밤.md` · `eval/questions_domestic_bonds.jsonl` |
| 08-31 | `619da1e` `fbc7e4d` `a4a2486` `5dff69b` `617160d` `760ed52` `37685c5` `638ed5c` `07727a5` `d6e1da6` `82359a6` `cd1898a` `28e6a18` `654c2c3` | **서버 실측 시작** — 날짜 산술폭탄 3겹 · 신용보강 지시문→가드 · 두 자리 연도 · 등급서열 IN 확장 · 국고채 확정식(STRIPS 리드 결정) · 최상급 안전 16 단독 · 종류 통칭 3종 · ESG (사)=사회적채권 확정 · 만기 정렬·싸다 되묻기·통화 값 사전 · 프로브10 후속 5건 · 0행 사유 자연어 · **`eda/domestic_bonds` 브랜치 main 병합** | `채권_프로브15_2026-08-30.md` · `채권_프로브10_실측_2026-08-31_밤.md` |
| 09-01 | `f91fff4` `ff54440` | 약점 프로브 — 날조 위험필터 제거 · 종류필터 WHERE 한정 · 추천 정렬 · **개수 질문 집계 강제** · 규칙 원문 `>` 오류 정정(`>=`) | `약점프로브_2026-09-01.md` · `재실측_체크리스트_2026-09-01.md` |
| 09-02 | `898dd56` `fc7fbe7` `f1e61d6` `03d0d98` `41d383f` `62807a7` `09853ed` `b780b78` `dbcab26` `c83986a` `07b2ef6` `05e1962` `f0fe676` | 3·4차 프로브(등급별집계·종류비교·필터컬럼표시·존재질문·금리유형·분포 조립) · **ABSENT 전수화·위험등급 `range_by_table`(KG 1R)** · 한전·삼성전자 실측 7건(값검사 TRIM 사각·대표행·만기제외·발행사 되묻기) · 조사 라우팅·구조 용어 · **채권 목록 기계 조립(HCX 0회)** · 기본 TOP-5 · **'가장 위험한' 결정층 되묻기** · **판정일 8/24**(리드) · 온톨로지·yaml 전수 재검증(1차 잔재 200곳) | `review_2026-09-02/*` · `kg_structure_probe_round*` |
| 09-03 오전 | `560e47a` `2de1e1c` | **제안서 채권 원고 1차**(04 §A~§F) · 회신 · **오답기록 50건** · 04장 흐름도 취합 · 05장 기대효과 · 부록 D API 명세 · NUMBERS 채권 절 편입 · 재실측 프로브 파일 | `docs/기술제안서/04_도메인_채권.md` · `채권_회신` · `채권_오답기록` · `10_흐름도_취합` · `11_기대효과_확장성` · `docs/API_SPEC.md` |
| 09-03 오후 | `ac4835d` `c8aa2b8` `1e6f279` `c899b15` `bf5908d` `b4d0d74` 외 | 사용자 직접 서버 실측 8문항 → **상대 시점 확정표**(내년·N년 뒤) · 발행사 되묻기 접두 `(주)` 2건 · **`curr_cd` 상수 게이트**(달러 채권 BAC 노출) + 오염 리터럴 기각 + 조립기 SELECT * 정리 · 무이자질의·영구채필터 규칙 · 영구채 콜 개시일 자동 병기 · 채권 종목 수 기계 조립 · 국고채 머리명사 판별 · 오답기록 #51~58 | `채권_오답기록` §2-7~2-13 · `채권_회신` §3 (형 결정 9건) |

---

## 3. 데이터 두 판 — 무엇이 어떻게 달라졌나

출처: [`DATA_V2_2026-08-24_impact.md`](DATA_V2_2026-08-24_impact.md) §2.1.

| 항목 | 1차 → 2차 | 우리 작업에 미친 영향 |
| :-- | :-- | :-- |
| 행 | 42,394 → 21,882 | 사라진 25,429행 중 67.5%가 만기 지난 것 |
| PK | `PD_NO` 하나 → 네 컬럼 | 🔴 `COUNT(*)` ≠ 종목 수 → 규칙 `대표행` + 가드 `ensure_bond_representative`·`ensure_distinct_count` |
| 새 컬럼 19개 | `bd_intp_tcd`(이표/복리/할인/단리) · `bd_inrt_tcd`(고정/변동/고정+변동) · `bd_ofr_tcd`(공모/사모) · `pd_risk_nm` · `trade_price` · `exg_close_*` … | 🟢 종목명 정규식 4종(사모·FRN·할인채·듀레이션0) 폐기 → 컬럼 직접 |
| 삭제 | `pd_evco_crd_grd`(평가사별 등급) | 🟢 `등급병합` 문제 소멸 |
| 신용등급 | 결측 41.1% → 18.4% · 표기 20 → 15종 | 서열은 여전히 데이터에 없음 → **코드북 + KG rank** |
| `crd_grd_dt` | "등급 미변경 시 과거 일자 유지" 스키마 코멘트 | 신선도 판단 금지 → 규칙 `등급일사용금지` |
| 패딩 | 여전히 있음(`bd_knd`·`pd_pbcm` 고정폭) | `TRIM` 규칙 + 가드 `ensure_trimmed_compare` + 값 검사기 TRIM 인식(09-02) |
| `buyable_quantity` | 주최 공지로 무효 | 구매가능 = `curr_cd='KRW' AND mat_dt >= 20260824` (판정일 8/24, 리드 09-02) |
| 기준일 셋 | — | 스냅샷 산출일 8/21(`info_base_dt`, remaining_days 기준) · 주최 as-of 8/22 · **질문 시점·판정·표기 8/24** — 규칙 `기준일` 이 셋을 구분 |

> 1차 엑셀은 `1.금융상품/_v1_20260711/` · 1차 DB 는 `data/financial_products.v1_20260711.db`. 두 판을 섞어 세지 않는다.

---

## 4. 우리가 만든 분류 체계 — 채권을 어떤 기준으로 가르는가

### 4-① 발행 주체 3층 (원본 컬럼) — 🔴 깔끔한 트리가 아니다

`std_pd_mcls_nm` 대분류 3종(회사채 12,865 · 특수채 6,177 · 국공채 2,840) → `std_pd_scls_nm` 소분류 13종 → `bd_knd` 채권종류 32종. 소분류 `일반사채`(회사채 12,133 / 특수채 614)·`특수은행채`(특수채 1,322 / 회사채 2)가 두 대분류에 걸쳐 **하위→상위 역추적 금지**. 통안채 33행은 대분류 **특수채**(09-02 정정 — 국공채 필터로는 0행). 분리채권(STRIPS) 209행은 `bd_knd` 결측 21 포함 — 종목명이 유일한 식별 수단이고, 국고채 확정식은 STRIPS 를 포함한다(리드 결정 08-31, `07727a5`).

### 4-② 특수구조 플래그 11종 (`name_encoding.special_structure_flags`, 종목명 정규식) — 2차 실측

콜 2,678 · 풋 529 · CB 389 · 후순위 530 · **영구 266행/237종목** · EB 137 · 분리채권 209(전부 할인채) · BW 32 · 코코 266(설명용 — 판정은 컬럼 신호: 은행 3종 + 위험등급 1~3 = 278행) · 물가연동 6 · PB 0. FRN·사모는 컬럼(`bd_inrt_tcd` 변동 830 + 고정+변동 148 · `bd_ofr_tcd` 사모 2,007)으로 대체. **ESG 라벨** `(녹)356·(사)1,984·(지)159` — `(사)` 는 사모가 아니라 사회적채권(팀 결정 08-31). 원칙: 겹치는 플래그라 카테고리가 아니라 **표시**(`구조표시` CASE 열)이며 추천에서 빼지 않는다 — 빼는 것은 `고위험제외`(1등급·C0·사모)뿐.

### 4-③ 구매가능·판매행·고위험제외 (2차)

- **구매가능** = `curr_cd='KRW' AND mat_dt >= 20260824` — 21,814행/20,431종목. 8/22·8/23 만기 14종목은 모수 밖, 8/24 당일 만기 20종목은 모수(`>=`). 가드 `ensure_cutoff_inclusive`·`raise_maturity_floor` 가 옛 리터럴을 교정.
- **판매행** = `buy_yield IS NOT NULL` 634 LOT(전부 장외) — "지금 파는" 질의 축. "살 수 있는" 과 다르다(약점프로브 #11 판정 정정).
- **고위험제외**(추천·랭킹만) = `pd_risk_gcd <> '11' AND COALESCE(TRIM(crd_grd),'') <> 'C0' AND bd_ofr_tcd <> '사모'` — ❌ `NOT(a OR b)` 는 무등급 국공채 2,840행이 NULL 로 사라진다(08-30 사고). 가드 `_rank_exclusions` 가 주입(만기 경과 제외 포함, 09-02).

### 4-④ 축 (`axis_derivation`) — 확정 3 · 미확정 4

| 축 | 상태 | 규칙 |
| :-- | :-: | :-- |
| couponType · offeringType · riskGrade | ✅ | `bd_intp_tcd` · `bd_ofr_tcd` · `pd_risk_gcd` 직접 (RiskGrade_0 = `'00'`) |
| issuerType · maturityClass · collateralType · issuerCategory | 🟡 `pending_workshop` | 대분류 단독+ISIN 접두 / 경계 미정 / 코드북 2차 재검수 전 / 키워드 오탐 62% — **프리즈 전 미착수, 제안서 한계 절에 명시** |

### 4-⑤ 코드북 — 채권이 쓰는 것

| 파일 | 역할 | 상태 |
| :-- | :-- | :-- |
| `data/external/lookups/credit_grade_scale.csv` | **신용등급 서열** — 한국기업평가 21행 · 표준등급 20(AAA~D) · DB 표기 `AA0`=AA · `C0`=C | ✅ `shared/credit_grade.yaml` 노드 21(등급 19 + 밴드 2)의 원천 · 게이트 표준표(`_load_std_grades`) |
| `collateral_type_map.csv` · `issuer_industry_map.csv`/`top200.csv` | 담보축·업종축 | 🟡 1차 기준 — 2차 재검수 전(§4-④) |
| `bond_issuer_background.md` | 발행기관 법정 손실보전 | ✅ 규칙 `신용보강` 6층의 근거 |
| `bond_tax_rules.md` · `bond_glossary.md` · `ktb_individual_structure.md` · `zeroin_methodology.md` | 세금·용어·개인투자용국채·위험등급 체계 | 배경 지식 |
| `ontology/shared/organization_issuer_auto.yaml` | 발행사 1,818 → Organization 노드 1,817 (자동 생성) | ✅ |

### 4-⑥ 등급 · 위험등급 — 이름이 비슷하지만 **다른 축**

- **신용등급** `crd_grd`(부도위험, AAA~C0 15종) — `AA0`→AA 정규화 · 국공채는 미부여가 정상 · "AA- 이상" 은 KG rank 서열로 `IN` 4종(규칙 `등급서열` + 가드 `expand_grade_comparison`) · 게이트 4분기(`not_grade`/`unknown`(AAAA)/`no_data`(BB+)/`ok`) 는 목록이 아니라 표준표 **형태** `^([A-D])\1{0,3}[+\-0]?$` 규칙.
- **위험등급** `pd_risk_gcd`(금리위험 포함, `'11'`=1등급 매우높은위험 … `'16'`=6등급 매우낮은위험, `'00'` 해당없음 19행) — **숫자가 클수록 안전**. 범위 **0~6** 은 `shared/risk_grade.yaml range_by_table` 한 선언에서 ttl 제약과 게이트 문구가 생성(09-02, 펀드·ETF 는 1~6).
- 둘은 다른 축 — 1등급 1,441행 중 AAA 1행, 921행 무등급 · C0 103종목은 전부 1등급(부분집합).
- **"위험한 채권"** 은 세 축(투자위험등급/신용등급/금리위험, ②③ 정반대)이라 축 단서 없으면 **결정층 되묻기**(`risk_ambiguity_clarify`, 리드 09-02). 🟡 사각: 회사채·공모 같은 종류 낱말이 단서로 잡혀 되묻지 않음(오답기록 §2-8, 형 결정 대기).

### 4-⑦ 결측 7유형 · 4-⑧ 역질문 — 초판 그대로 유효

빈칸 판정 순서 ⑦정상값(`srfc_irt=0`)→⑤⑥센티넬·복사→④복구가능→①②③(구조적 없음·상태·미계산). 역질문은 3단 기준(데이터로 결정 / 기본값+명시 / 되묻기) — 현행 `clarify` 다의어 6(수익률·위험·등급·만기·싸다·가격) + 사람의_선택 4 + 조건부 1. **08-30 결정: 무응답 기본값은 복원하지 않고 되묻기로**(Single-turn). '싸다'·'위험' 은 결정층 가드로 승격.

---

## 5. 규칙 현황판 — `query_rules` 40종 (2026-09-03 · yaml 파서 기준)

> 1차 16 → 2차 20(08-25) → 26(08-30) → 38(09-02) → **40**(09-03). 규칙은 SQL 생성기 프롬프트에 실리고, 그중 "실렸는데 무시된" 것은 가드로 승격됐다(→ 열).

| 묶음 | 규칙 | 승격된 가드(§8-3) |
| :-- | :-- | :-- |
| 행·모수 | 대표행 · 판매행 · 구매가능 · 개수질문 · 존재질문 · 추천개수정렬 · 고위험제외 · 기준일 · 만기윈도우 · 날짜표기 | `ensure_bond_representative` · `ensure_distinct_count` · `ensure_count_query` · `ensure_positive_count_answered` · `_zero_count_answer` · `_bond_count_answer` · `ensure_default_topn` · `_rank_exclusions` · `normalize_date_literals` · `ensure_maturity_lower_bound` · `ensure_cutoff_inclusive` · `raise_maturity_floor` · `align_maturity_year` · `enforce_relative_window` |
| 등급 | 등급서열 · 등급정규화 · 위험등급방향 · 수익최상급조회 · 필터컬럼표시 · 등급별집계 · 등급일사용금지 · 장외등급해석 | `expand_grade_comparison` · `ensure_top_safety` · `strip_fabricated_risk_filter` · `ensure_grade_select_column` · `ensure_risk_name_column` · `_distribution_answer` |
| 종류·구조 | 종류필터 · 종류비교 · 발행사조회 · 신용보강 · 구조표시 · ESG라벨 · 금리유형 · 공모사모판정 · 유동화위험금지 · **영구채필터**(09-03) | `ensure_kind_filter` · `ensure_ktb_kind`(+ `ktb_head_is_gov`) · `ensure_credit_backstop` · `_suggest_similar_issuers`·`_issuer_clarify_text` · 조립기 콜 개시일 병기 |
| 값·컬럼 | 문자열비교 · 영값배제 · 수익률정상 · 듀레이션정상 · 익일값 · 이자유형분리 · 장내종가 · 과세수익률금지 · 더티금지 · 시장집계금지 · 외화채없음 · **무이자질의**(09-03) | `ensure_trimmed_compare` · `forbidden_column_use` · `forbidden_literal_use`(`curr_cd='000'`) · `ensure_maturity_sort` · `ensure_reco_sort` · `ensure_bond_evidence_columns` · `_bond_list_answer` |

그 밖의 yaml 절: `synonyms` 47(통칭·약칭·구조 용어·**무이표·무이자·제로쿠폰**) · `answer_rules` 20(말하는 법 — 국공채 미부여 · 기준일 8/24 · 순서대로 전사 · 조건부 주의 문구 …) · `clarify` 11 · `name_encoding` 4묶음 · `normalization`(trim 13컬럼·grade_suffix·zero_as_missing) · `gate_constants` 1(`curr_cd`) · `absent_properties` 1(`hasCreditGradeHistory`) · `axis_derivation` 3+4 · `workshop` 2. 규칙 원문(압축 전 이력)은 [`채권_규칙_원문_2026-08-30.md`](review_2026-08-26/채권_규칙_원문_2026-08-30.md).

---

## 6. 08-26 발견의 2차 재검증 — ✅ 09-02 완료

초판 §6 의 🟡 묶음(지역개발채 오분류·키워드 오탐·무보증 건수·파킹·0등급·듀레이션 45일·`is_callable`)은 **09-02 온톨로지·yaml 전수 재검증**(`f0fe676` · `05e1962`)에서 2차 DB 로 다시 돌렸다 — 분류 모순 1건(통안채 = 특수채)·수치 drift 4건 정정, 여전채 어휘 신설. 남은 🟡 는 담보·업종 코드북(§4-④ pending) 하나이고 프리즈 전 범위 밖으로 확정했다. 위험등급 런타임 미반영(F-2-10)은 08-30 규칙 + 08-31 가드로 닫혔고, 규칙 실행성(F-2-3)은 09-02 "규칙 전달 감사"(리드, `3ad9189`·`67534e6`)로 측정됐다 — 실렸어도 무시되는 유형은 **결정층 가드**로, 그 목록이 §5 의 → 열이다.

---

## 7. 문서 지도 — 무엇을 보려면 어디로

| 알고 싶은 것 | 문서 | 판 |
| :-- | :-- | :-: |
| 채권이 뭔지 · 컬럼 뜻 | [`domain/domestic_bonds.md`](domain/domestic_bonds.md) | 개념 |
| 58컬럼 사전(결측·단위·규칙 자동 생성) | [`핵심문서모음/12_데이터사전_data_dictionary/bonds.md`](핵심문서모음/12_데이터사전_data_dictionary/bonds.md) (`gen_data_dictionary.py`) | **2차** |
| 온톨로지 규칙 12종(지칭·결측·grain·모수·파생·배타·단위·금지·부재·계층·기준일)에서 채권 항목 | [`ontology_rules/`](ontology_rules/README.md) 01~12 | **2차** |
| 판정·규칙 정본 | `ontology/enums/domestic_bonds.yaml` (§5) | **2차** |
| 1차 구조도·EDA·검토 답글·추가 검토 | `domain/domestic_bonds_graph.md` · `eda/domestic_bonds_notes.md` · `review_reply_bonds_2026-08-21.md` · `additional_bonds.md` | 1차 |
| 2차 전환·재검증 | `DATA_V2_2026-08-24_impact.md` · `review_recheck_2026-08-25.md` · `review_yaml_pending_2026-08-25.md` | 2차 |
| 검토 17건 판정 · 전수조사 · 재점검 · 규칙 원문 | [`review_2026-08-26/`](review_2026-08-26/) 채권_검토기록_08-27 · 채권_전수조사_08-30 · 채권_재점검_08-30_밤 · 채권_규칙_원문_08-30 | 2차 |
| 서버 실측 프로브·수리 | 채권_프로브15_08-30 · 채권_프로브10_실측_08-31_밤 · 약점프로브_09-01 · 재실측_체크리스트_09-01 · [`review_2026-09-02/한전_삼성전자_실측_수정계획`](review_2026-09-02/한전_삼성전자_실측_수정계획_2026-09-02.md) | 2차 |
| **오답 58건 전수(질문→오답→원인→수정→상태)** | [`기술제안서/채권_오답기록_2026-09-03.md`](기술제안서/채권_오답기록_2026-09-03.md) | 2차 |
| **제안서 채권 원고** (§A 데이터 · §B 결함→선언 5+1 · §C 흐름도 · §D 현업 · §E 부록 · §F 재현 SQL) | [`기술제안서/04_도메인_채권.md`](기술제안서/04_도메인_채권.md) · 회신 [`채권_회신_2026-09-03.md`](기술제안서/채권_회신_2026-09-03.md) | 2차 |
| 제안서 횡단 장(채권 담당) — 04장 흐름도 취합 · 05장 기대효과 · 부록 D API | `기술제안서/10_흐름도_취합.md` · `11_기대효과_확장성.md` · [`API_SPEC.md`](API_SPEC.md) | 2차 |
| 설계 철학 · 오답 유형 구조해법 | `기술제안서/08_설계철학.md` · `09_오답유형_구조해법.md` | — |
| 수치 단일 출처 | [`proposal/NUMBERS.md`](proposal/NUMBERS.md) §1 국내채권 | **2차** |
| 온톨로지 확장·KG 구조 검증 | `kg_structure_probe_design_2026-09-02.md` · `kg_structure_probe_round1~9` (KG35: 기준선 ✅5 → 9R ✅24) | 2차 |

### 낡은 숫자 주의 — 문서에 남아 있지만 이제는 틀린 것

| 숫자 | 상태 | 지금 맞는 값 |
| --: | :-- | :-- |
| 41.1% / 41.6% 신용등급 결측 | ⚫ 1차 | **18.4%** (4,020/21,882) |
| 25 / 38 / 39 `query_rules` | ⚫ 구본·오기 | **40** (yaml.safe_load 기준) |
| 15,806 OFFICIAL-001 모수 | ⚫ 8/22 판정 | **15,792** (8/24 판정) |
| `mat_dt >= 20260822` 구매가능 21,828 | ⚫ 8/22 | **`>= 20260824` 21,814행 / 20,431종목** |
| 3,036 유동화 · 187 코코 · 450 영구채 · 254 매수가능 · 16,349 시장 | ⚫ | 4,045 · 266(컬럼 판정 278) · 266행/237종목 · 634 LOT · 20,497 |

---

## 8. 최종 코드·산출물 인벤토리 — "결국 어느 파일이 정본인가" (2026-09-03)

### 8-1. 선언 — 사람이 쓰는 원천 (여기만 고친다)

| 파일 | 줄 | 무엇 |
| :-- | --: | :-- |
| `ontology/enums/domestic_bonds.yaml` | 931 | **채권 판정·규칙 정본** — row_grain · columns 58(missing_reason none 22 · not_applicable 16 · missing 14 · mixed 6 / kg_entity Organization·Currency·RiskGrade / unit percent 14·krw 9…) · name_encoding · normalization · query_rules 40 · synonyms 47 · answer_rules 20 · clarify 11 · axis_derivation · gate_constants · absent_properties |
| `ontology/enums/domestic_bonds.auto.yaml` | 1,562 | 기계 사실(결측률·distinct·값 목록) — 생성물, 손대지 않음 |
| `ontology/enums/domestic_bonds.vocab.yaml` + `*.values.txt` | 209 + 6 | 값 사전(커버리지 ≥98% 컬럼) — `gen_value_vocab.py` 생성 |
| `ontology/shared/credit_grade.yaml` | 162 | CreditGrade 노드 21 = 등급 19(rank 1~19) + 밴드 2(`skos:broader`) · `crd_grd` alias 15 |
| `ontology/shared/risk_grade.yaml` | 89 | RiskGrade 7(0~6) · **`range_by_table`** 채권 0~6 · alias `'11'~'16'`·`'00'` |
| `ontology/shared/organization_issuer_auto.yaml` | 18,188 | 발행사 Organization 1,817 노드(자동) |
| `ontology/shared/currency.yaml` | 76 | Currency 8 · 채권 alias KRW 1 |
| `data/external/lookups/credit_grade_scale.csv` | 21행 | 등급 서열 코드북(출처·기준일 컬럼 필수) — KG rank 와 게이트 표준표의 원천 |

### 8-2. 생성물 — 빌드가 만든다 (손으로 고치지 않는다)

| 산출물 | 생성기 | 내용 |
| :-- | :-- | :-- |
| `ontology/bond_kr.ttl` (36줄) · `common.ttl` 채권분 | `scripts/build_ontology.py` (검증 V1~V7) | `fp:DomesticBond` · `couponRate`·`duration` 주석 · **ABSENT 4** · `riskGradeValue_DomesticBond` 0~6 제약 |
| KG 4테이블 (`kg_node`·`kg_alias`·`kg_edge`·`kg_closure`) 채권분 | 〃 | alias CreditGrade 15 · RiskGrade 7 · Currency 1 · Organization 1,818(노드 1,817) · closure CG 밴드→등급 19 |
| `docs/proposal/NUMBERS.md` §1 국내채권 | `scripts/gen_proposal_numbers.py` | 행·종목·구매가능·공식예시 모수·결측·등급·발행사·할인채·영구채·되묻기 규모 |
| `docs/핵심문서모음/12_데이터사전…/bonds.md` | `scripts/gen_data_dictionary.py` | 58컬럼 사전 |
| `docs/ontology_rules/01~12.md` | `scripts/gen_ontology_rules_doc.py` | 규칙 12종 문서(채권 항목 포함) |
| `data/financial_products.db` | `scripts/build_db.py` (엑셀 → SQLite) | 마스터 4 + ext + KG + schema_metadata |

### 8-3. 런타임 — 채권이 지나는 층과 함수 (`src/runtime/`)

| 층 | 파일 · 함수 | 역할 |
| :-- | :-- | :-- |
| Route | `router.py` `route()` — 머리명사 + DB 값 + `synonyms`(조사 허용 `_bound_in`) | "채권·국고채·여전채·무이표…" → `domestic_bonds` |
| Ground | `pipeline._ground` (타 테이블 alias fallback 제거) · `loader._build_value_index` 전 값 | `AA-`→`CG_AAm` · `한전`→발행사 등호 |
| Gate (3층, HCX 0회) | `gate.py` `check()` — ABSENT(`absent_properties`·`absent_in`) · `classify_grade_token` 4분기(`_GRADE_SHAPE`) · `gate_constants`(`curr_cd`) · `range_by_table` 위험등급 · `future_tokens`/`sql_uses_as_maturity` 사후검사 · **`resolve_relative_window` 확정표**(09-03) · 상수 `DATA_CUTOFF=BUYABLE_CUTOFF=2026-08-24`, `SNAPSHOT_DATE=2026-08-21` | 존재하지 않는 등급·외화 채권·7등급·등급 이력 즉답 |
| 결정층 되묻기 | `pipeline.price_ambiguity_clarify`(싸다) · `risk_ambiguity_clarify`(위험 세 축, 축별 규모 DB 실측) | HCX 전 되묻기 |
| Plan | `build_grounding` — KG 매핑 + 규칙 2층 + clarify + `_refusal` + 스키마 (채권 약 22,400자) · `planner.SQL_CONFIG.max_tokens 1536` | HCX SQL 생성 |
| Guard (생성 후 교정) | §5 → 열의 함수들 + `validate_sql` · `guard.check_values`(값 사전 대조, TRIM/COALESCE 인식) · `forbidden_column_use`/`forbidden_literal_use` · `ensure_trimmed_compare` · `normalize_table_names` | 규칙을 무시한 SQL 을 기계로 되돌림. 재생성 1회 |
| Execute | SQLite 읽기 전용 | — |
| 조립 (HCX 0회) | `_bond_list_answer`(목록 — 머리줄 전체 N종목·정렬축·기준일, 콜 개시일 병기, SELECT * 핵심 항목만) · `_bond_count_answer`(단일 COUNT) · `_zero_count_answer`(0집계 + 발행사 되묻기 `_suggest_similar_issuers`) · `_distribution_answer`(분포) · `ensure_top_row_cited`·`ensure_positive_count_answered`(HCX 답 교정) · `_cell`(잔존일수 `N일(약 X년)`, 날짜 정수) | 답변 문장을 규칙으로 |

### 8-4. 검증·평가 자산

| 자산 | 내용 |
| :-- | :-- |
| `eval/questions_domestic_bonds.jsonl` | **36+문항** gold(SQL·행·sample·검증자) — BND-D/A/R/C/U/F 유형, 회귀 문항 25~36 은 실측 오답 원형 |
| `eval/questions_top_safety_probe.jsonl` | 안전 최상급 10문항(BND-S) |
| `eval/questions_official_sample.jsonl` | OFFICIAL-001(AA- 이상, 모수 15,792) · OFFICIAL-NA-001(AAAA) |
| `eval/probe_bond_recheck.txt` | 재배포 후 서버 재실측 **29문항**(8/31 체크리스트 18 + 9/3 발견 11) — `eval/probe_server.py` 로 실행 |
| `eval/run_gold_check.py` | 로컬 gold 전건(09-02: 147 통과/실패 0) |
| `tests/` | 채권 언급 test_runtime 135 · test_guard_v2 44 · test_improvements 16 · test_router 8 (전체 490 passed, 09-03) |
| `scripts/audit_bonds_rules.py` · `audit_bonds_claims.py` · `audit_bonds_questions.py` | yaml 문장의 숫자·조건식 DB 재현(112건) · 문서 주장 재현 · gold 문항 감사 |
| 서버 실측 기록 | `docs/기술제안서/채권_오답기록_2026-09-03.md` §1 총괄표 58건 · §2 날짜순 |

### 8-5. 배포 — 고친 것이 서버에 가는 길

`git push`(main) → 서버 `git pull`. `enums/*.yaml` 만이면 `bash deploy/deploy.sh --yaml-only`(5초) · `shared/*.yaml` 이면 `build_ontology.py` → `--db-only` · **코드(`src/`)면 `--code-only`**. 09-03 오후 수정은 yaml+코드라 코드 재배포가 필요하다(`DEPLOY.md` §0).

---

## 9. 2차 DB — ✅ 로컬 = 배포본 = 주최 원본

`data/financial_products.db`(v2_20260824, 채권 21,882행). 08-30 에 주최 2차 엑셀로 별도 빌드해 행 단위 해시 대조 — 4테이블 53,375행 + schema_metadata 280행 전부 동일. `1.금융상품/`·`data/` 는 `.gitignore` 라 git 이 관리하지 않는다(드라이브 공유).

---

## 10. 결론 — 결국 뭐가 확정됐고, 뭐는 되물어야 하고, 뭐는 답을 못 하나 (2026-09-03)

> 초판 §10 의 항목은 유지하고 8/30 이후 확정·변경만 표시한다(🔄 변경 · 🆕 신규). 근거 건수는 전부 2차·판정일 8/24.

### 10-A. ✅ 확정 — 그냥 답하면 되는 것

| 항목 | 확정 내용 | 근거 |
| :-- | :-- | :-- |
| 🔄 기준일 | 답변 표기·구매가능 판정 **2026-08-24** · 스냅샷 산출일 8/21(잔존일수는 이 날 기준, 병기) · as-of 8/22 는 데이터 설명에만 | 리드 09-02 · 규칙 `기준일`·`구매가능` · `gate.DATA_CUTOFF` |
| 🆕 상대 시점 | 오늘 = 8/24 고정 · 내년·N년 뒤 = 그 해 전체 · N년 안에 = D+N년 — 확정표가 SQL 창을 교체 | `gate._RELATIVE_WINDOW` · `enforce_relative_window` · 규칙 `만기윈도우` (오답기록 #51·#53) |
| 행 ≠ 종목 | 종목 수 = `COUNT(DISTINCT pd_no)` / 목록은 `GROUP BY pd_no` · 속성이 다른 8종목은 병기 | 규칙 `대표행` · 가드 |
| 🔄 구매가능·판매행 | `curr_cd='KRW' AND mat_dt >= 20260824` 20,431종목 / 판매조건 634 LOT | 규칙 `구매가능`·`판매행` |
| 신용등급 서열·정규화 | "AA- 이상" = `IN('AAA','AA+','AA0','AA-')` · `AA`→`AA0` · 국공채 미부여 / 회사채·특수채 미수록 · 등급일로 신선도 판단 금지 | KG rank · 규칙 `등급서열`·`등급정규화` · 가드 |
| 위험등급 방향·범위 | 숫자 클수록 안전 · 범위 0~6(`'00'` 19행은 값) · "가장 안전" = `'16'` 단독(6등급 없는 종류는 `IN('15','16')` 폴백) | `range_by_table` · 규칙 `위험등급방향` · `ensure_top_safety` |
| 🔄 고위험제외·구조표시 | 추천·랭킹만 1등급·C0·사모 제외(NULL-안전) + 만기 경과 제외 · 특수구조는 빼지 않고 표시 · 6% 초과·2·3등급이면 주의 문구 · 기본 TOP-5 + 전체 종목 수 병기 | 규칙 `고위험제외`·`구조표시`·`추천개수정렬` · `_rank_exclusions`·`ensure_default_topn` |
| 🆕 영구채 | `신종\|영구` 266행/237종목 · `mat_dt` = 콜 개시일 → 답변에 "만기일 = 콜 개시일" 자동 병기 | 규칙 `영구채필터` · 조립기 (오답기록 #57) |
| 🆕 외화·달러 채권 | 원화만 수록 — 어휘 게이트 HCX 0회 · `curr_cd='000'` 오염값 1행(BAC)은 조건·답변에 쓰지 않음 | `gate_constants curr_cd` · `forbidden_literal_use` (오답기록 #55) |
| 🆕 무이자·무이표 | 할인채 686종목(발행 할인) 기본 + 표면금리 0 577종목(주식연계 488) 병기 · 이유는 서술 금지 | 규칙 `무이자질의` (오답기록 #56) |
| 🆕 발행사 | KG 별칭 등호(한전 → 한국전력공사(주) 386종목; LIKE 는 대한전선 오포함) · 없는 발행사(삼성전자 0)는 같은 어두 발행사 되묻기(삼성카드 323…) — 앞뒤 `(주)` 벗겨 비교 | 규칙 `발행사조회` · `_suggest_similar_issuers` (#43·#54) |
| 🆕 종류 통칭 | 국고채 = 국고채권 + STRIPS 결측(295) · 은행채 2종 · 지방채 3종 · 여전채 3종 · 회사채 = 대분류 · 통안채 = 특수채 · 종류 비교는 CASE 단일 쿼리 | 규칙 `종류필터`·`종류비교` · `ensure_ktb_kind` |
| 🆕 목록·집계 답변 | 채권 목록·단일 COUNT·0집계·분포는 **기계 조립**(HCX 0회) — 정렬 순서 그대로, 모수·기준일 머리줄, 조건부 주의 문구 | `_bond_list_answer`·`_bond_count_answer`·`_zero_count_answer`·`_distribution_answer` |
| 유동화·더티·익일·시장집계·장외등급·표면금리 정렬·장내종가·세금·문자열 TRIM | 초판 §10-A 그대로 | 규칙 `유동화위험금지`·`더티금지`·`익일값`·`시장집계금지`·`장외등급해석`·`이자유형분리`·`장내종가`·`과세수익률금지`·`문자열비교` |
| ESG 라벨 | `(녹)(사)(지)` 는 녹색·사회적·지속가능 채권 표기 — `(사)` ≠ 사모 | 팀 결정 08-31 · 규칙 `ESG라벨`·`공모사모판정` |

### 10-B. ❓ 되묻기 — 사용자에게 물어봐야 답이 정해지는 것

**원칙**(08-30 결정): 무응답 기본값은 쓰지 않고 되묻는다 — Single-turn 이라 되묻기가 곧 최종 응답이고 유효 답변으로 채점된다. 되묻기 전 모수가 0이면 "없다 + 이유"로 답한다(발행사 0건 → 유사 발행사 제시).

| 항목 | 갈리는 축 | 층 | 상태 |
| :-- | :-- | :-- | :-- |
| **위험** ("가장 위험한 채권") | ① 투자위험등급 1등급 1,394 / ② 신용등급 C0 103(①의 부분집합) / ③ 금리위험(국공채 장기물) | **결정층** `risk_ambiguity_clarify` — 축 단서 있으면 되묻지 않음 | ✅ 서버 실측 0.3초 · 🟡 사각: 회사채·공모 단서, '위험도' 접사(형 결정) |
| **싸다·저렴** | 가격 낮음 / 수익률 높음 | **결정층** `price_ambiguity_clarify` | 🔧 서버 재실측 대기(BR-P03) |
| 수익률 · 등급 · 만기 · 가격 | 표면/민평/매수/세후 · 신용/위험 · 만기일/잔존/듀레이션 · 평가단가/매매단가/장내종가 | 2층 `clarify.다의어` (프롬프트 → HCX `CLARIFY:`) | 🟡 HCX 재현 비결정 — gold BND-C-016·017 실측 대기 |
| 보유기간 · 안전의 정의 · 투자기간 · 답변모수 | 사람의 선택 | 2층 `clarify.사람의_선택` | 〃 |
| 존재하지 않는 상품명 | 정확일치 0 → 유사 후보 4 | `[Suggest]` (KODEX AI로봇 → KODEX 로봇액티브 …) | ✅ |

### 10-C. ⛔ 답 못 하는 것

**10-C-1. 🟡 우리가 더 하면 풀리는 것 (프리즈 전 후보 · 형 결정 9건은 `채권_회신` §3)**

| 무엇 | 왜 막혀 있나 | 풀리는 조건 |
| :-- | :-- | :-- |
| 서버 재실측 공백 | 오답 58건 중 서버에서 정답 재확인 9건 · 나머지는 로컬 수정·gold 통과 | 재배포(yaml+code) 후 `probe_bond_recheck.txt` 29문항 |
| '위험' 되묻기 사각 2 · 값 검사 컬럼 자동 교정 가드 · `SELECT *` SQL 층 치환 · 값 사전 "사용 금지 값" 표식 · `_GRADE_SCALE` 코드 상수 → KG rank | 코드(리드 판단) | 회신 §3 |
| 담보·업종·만기구간 축 | 코드북 1차 기준 · 경계 미정 | 프리즈 전 범위 밖 — 제안서 한계 절 |
| 신용등급 결측 18.4% | 외부 원천 없음 | 보완 불가 — "미부여/미수록" 으로 답하는 것이 정답 |

**10-C-2. 🔴 데이터로는 영영 못 푸는 것** — "제공 데이터로는 확인할 수 없습니다 + 이유 + 대안" (초판 표 그대로): AT1 여부 미확정 2건 · 지방채 상환구조 11건 · 카드·할부 듀레이션 45일 331건 · `mat_dt=0` 5행 · 위험등급 `'00'` 19행의 정의 · `ndy_*` 복사 이유 · `bd_knd` 결측 152·발행사 결측 149 · 이름에 표기 없는 특수구조 · 담보 확신 B(관행 추정) · **등급 이력·발행사 재무·투자전략 동향**(ABSENT).

### 10-D. 한 장 요약

```
질문이 들어오면
 ├─ Route → Ground(값 접지) → Gate: 부재·표준표 밖 등급·상수 컬럼(외화)·범위 밖 등급 → HCX 0회 즉답
 ├─ 결정층 되묻기: '위험'·'싸다' 축 단서 없음 → 세 축/두 축 제시하고 되묻기
 ├─ Plan(HCX SQL) → Guard 30여 종이 규칙 위반을 기계로 교정/기각(재생성 1회)
 ├─ Execute → 조립: 목록·COUNT·0집계·분포는 HCX 0회, 서술형만 HCX
 └─ 10-C-2 → "확인할 수 없습니다" + 이유 + 대안 (되묻지 않는다 — 사용자도 모르는 정보)
```

---

## 11. 남은 일 (2026-09-03 밤 기준)

1. **재배포**(코드+yaml) → `eval/probe_bond_recheck.txt` 29문항 서버 실측 → 오답기록 §5 갱신 · 제안서 04 §B·§C 서버 원문 교체
2. 회신 §3 형 결정 9건 회수 — 특히 '위험' 되묻기 사각(정규식 2줄) · 컬럼 자동 교정 가드 · `SELECT *` 치환
3. gold 승격 3건(BND-D-037 "3년 뒤" 2,611 · BND-U-038 "달러" reject · 무이자 채권) — 다른 세션과 jsonl 충돌 주의(pull 먼저)
4. 제안서 — 04 흐름도 4개 취합 `▶`(형 판단 2건) · 05 §D 펀드 한 문장 · API 명세 URL 확인 · 9/5 PDF 조판 · 루트 README 여부
5. 이 문서는 지도다 — 새 사실이 생기면 오답기록·yaml 에 쓰고 여기엔 링크만 더한다.
