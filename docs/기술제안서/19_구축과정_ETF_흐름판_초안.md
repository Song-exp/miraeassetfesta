# 구축 과정 — ETF 국내·해외 (흐름판 초안 · 2026-09-04)

> ## ⚠️ 읽기 전에 — 이 문서의 상태 (2026-09-04 · 리드 검토 전 초안)
> - **성격**: 병철의 `17_구축과정_ETF.md`(여섯 걸음 + 실례 3건)를 흐름 순서로 재배열한 것. **17 은 손대지 않았고 정본은 05·16·17** — 다르면 그쪽이 맞다.
> - **`▶` 8곳**: 전부 yaml 을 직접 파싱해 센 값(상위 키 15/15 · kg_entity 12/6 · answer_rules 28 · yaml 줄 수 1,274/768 · audit 검사 31건). §2.1 answer_rules 는 17 원고의 26 과 다르다(28) — 어느 쪽이 최신인지 ETF 담당이 확정.
> - **`[리드 검토]` 5곳**: §2.1 해외 ABSENT 가 shared `absent_in` 에서 오는 서술 · §5.4 V1·V2 의 ETF 실례 2건 · §6.2 해외 위험등급 기각의 서버 trace 원문 부재.
> - **얇은 절**: §5.3 은 ETF 몫만의 노드 수가 NUMBERS 에 없어 전체 노드 수 + 원천 컬럼 값 수로 대체했다. §6.2 는 흐름만 있고 trace 원문이 없다 — 서버에서 한 번 받아 붙이면 된다.
> - **해외 총보수 0값은 05 의 419건을 썼다.** DB 직접 집계는 368(0값만, NULL 제외) — 정의 차이. 조판 전 05 에서 정의를 명시.
> - **ETF 담당이 할 일**: answer_rules 26/28 확정 · §6.2 trace 붙이기 · 05·17 과 어긋나는 문장은 이 문서를 고친다.

> 한 줄: 이 문서는 "원본 데이터 → yaml → 외부 수집 → yaml 완성 → 온톨로지·KG → 질의 답변" 순서로 ETF 도메인이 어떻게 만들어졌는지 적는다. 정본 원고는 `05_도메인_ETF.md`·`16_ETF_본문원고.md`, 판정 실례는 `17_구축과정_ETF.md`(병철). 이 문서는 17 의 재료를 흐름 순서로 재배열한 것이다.
>
> 표기: `▶` = 직접 세어 넣은 수치(조판 전 재실측) · `[리드 검토]` = 확실하지 않은 서술. 수치 우선순위는 `docs/proposal/NUMBERS.md` > 05·16·17.

---

## 0. 한 장 요약

| 단계 | 입력 | 산출물 | 시기 |
| :-- | :-- | :-- | :-- |
| 1. 원본 EDA | `domestic_etfs` 1,780×98 · `overseas_etfs` 6,037×49 (기준일 2026-08-22) | `docs/eda/domestic_etfs_notes.md` · `overseas_etfs_notes.md` · 발견 목록 | 1차 데이터 2026-08-11 착수, 2차(8/22 배포)로 재실측 8/25 |
| 2. 1차 yaml | EDA 발견 | `ontology/enums/domestic_etfs.yaml` · `overseas_etfs.yaml` 첫 판(컬럼 판정·규칙) | 국내 2026-08-10 첫 커밋 · 해외 08-11 |
| 3. 외부 수집 | 마스터에 없는 구성종목 | `ext_etf_holdings` 75,859행 · `ext_ovs_etf_holdings` 906,848행 | 방법 확립 08-16(7/10 본) → 스크립트 08-20 → 8/21 본 재수집 → 적재기 08-25 |
| 4. yaml 완성 | 외부 데이터 · 서버 오답 | `external_join`·`derivation_rules`·`gate_constants`·`absent_properties`·`triggers` 추가 | `external_join` 확정 08-27 · 트리거 08-30 · ABSENT 09-02 · 이후 계속 |
| 5. 온톨로지·KG | enums·shared yaml · 코드북 | `ontology/etf_kr.ttl`(34줄)·`etf_gl.ttl`(21줄) · `kg_node/alias/edge/closure` | `build_ontology.py` 08-18 신설, 마지막 09-02 |
| 6. 질의·답변 | 사용자 질문 | 공식 예시 #3 14건(9/4) · 답변불가 기각 | 서버 실측 08-31 ~ 09-04 |

전 단계를 관통하는 규율 둘(17 §0): **값을 고치지 않는다**(판정만 기록) · **수치는 전부 실측**.

## 1. 원본 데이터 EDA — 무엇을 읽었나

### 1.1 두 테이블 개요

| | 국내 `domestic_etfs` | 해외 `overseas_etfs` |
| :-- | :-- | :-- |
| 원본 | `pref01n001_data.xlsx` (v2_20260824) | `pref02n001_data.xlsx` (v2_20260824) |
| 행 × 컬럼 | 1,780 × 98 | 6,037 × 49 |
| 기준일 | 2026-08-22 | 2026-08-22 |
| 행의 낟알 | 행 = 상품, `pd_itm_no` 완전 유일 | 행 = 상품, 티커에 `.K`/`.O` 접미어 |
| ETF / ETN | 1,235 / 545 (ETN 30.6%) | 5,972 / 65 (ETN 1.1%) |
| 종류 판별 컬럼 | `pd_grp_no` | `pd_grp_no` (보조 `cu_etn_yn`) |
| 언어 | 상품명 한글, 지수명 영문 | 자산군·지역까지 영문 |

1차 데이터(7/11 스냅샷, 1,734행 × 73컬럼)로 시작해 2차(8/22)로 전부 재실측했다. 1차 노트의 수치는 재실측 전까지 쓰지 않는다.

### 1.2 발견

| # | 발견 | 국내 | 해외 | 어디로 갔나 |
| :-: | :-- | :-- | :-- | :-- |
| 1 | ETN 혼입 — "ETF 테이블" 이름이 거짓말 | 545건 (30.6%) | 65건 | §2.2 · §4.2-1 |
| 2 | 총보수 0 = 미입력 | 유효 67건, 0·NULL 1,713행 | 0값 419건 | §4.2-3 |
| 3 | 레버리지 부호 소실 (2차에서 인버스가 양수로) | 상품명 '인버스' 225 vs 음수 23 | 플래그 `cu_inverse_short_yn` 단독 8건 누락 | §4.2-4 |
| 4 | 위험등급 컬럼 부재 | 있음 (1~6) | **컬럼 자체 없음** | §4.2-2 |
| 5 | 원천 이원화 — 같은 정보가 두 컬럼 (`cu_`/`ref_`, `wu_`/`ref_`) | 운용사·지수·지역·자산군 4축 (지수는 `ref_` 정본, `cu_` 95.5% 공백) | 없음 (단일 원천) | §2.1 kg_entity |
| 6 | 지역 삼중 표기 | 한글 11종 + 영문 `ref_geo_focus` 23종 | 영문 59종 | §4.2-6 |
| 7 | 지역 오분류 (원천이 틀림) | 43건 (미국 28·중국 15, 예: `TIGER 미국S&P500선물(H)` → '국내') | — | §4.2-6 · §7 |
| 8 | 자산군 오분류 · 섹터 컬럼 부실 | `pd_sect_cd` 로 섹터 찾으면 recall 20% | — | 규칙 `섹터테마질의` |
| 9 | 상수 컬럼 | `cu_charge_etc_rt` 전건 0 | `pd_trd_ccy` 전부 USD · `pd_mkt_id` 전부 US · `pd_sale_yn` 전부 1 | §4.2 `gate_constants` |
| 10 | 이름이 두 벌 | 약어명 ⊂ 정식명 55%뿐, `pd_nm='KODEX 200'` 완전일치 0건 | 티커 `ZZZZ` vs 실재 `ZZZ.O` | 규칙 `상품명조회` |
| 11 | 식별자 겹침 | — | ISIN 63종이 2상품에 걸림 | §3.3 ISIN 조인 금지 |
| 12 | **구성종목 컬럼 없음** | 없음 | 없음 | §3 전체 |

빈 값은 채우지 않고 넷으로 갈랐다(16 §2-2): 미입력 0(총보수) · 센티넬(-100) · 위장 결측(상장일 0, 지수명 'not provided') · 구조적 부재(해외 위험등급). 값을 고치지 않은 대가로 답변마다 모수를 밝힌다.

### 1.3 어떻게 봤나

| 도구 | 역할 | 비고 |
| :-- | :-- | :-- |
| `docs/eda/domestic_etfs_notes.md` · `overseas_etfs_notes.md` | 컬럼별 프로파일 · 결측 판정 · 축 검증 (해외는 국내와의 차이점 위주) | 2026-08-11 착수 |
| `scripts/audit_etf_claims.py` | DB ↔ yaml ↔ KG 삼각 대조. yaml 의 수치 주장·규칙 조건식·KG alias 를 2차 DB 로 재현해 불일치만 앞에 모은다 | 검사 31건▶ · 2026-08-31 |

커버리지: 국내 98·해외 49 컬럼 전부 판정해 yaml `columns:` 에 적었다(17 §1). `audit_etf_claims.py` 가 잡는 것은 yaml 에 적힌 수치 주장이 2차 DB 와 어긋나는 경우다 — 예: "ETF 1,235·ETN 545", "보수유효 67", "-100 센티넬 1y 110".

## 2. 1차 yaml — 판정을 선언으로

### 2.1 두 yaml 의 구조

한 파일이 한 테이블이다. 상위 키는 국내 15개·해외 15개▶.

| 키 | 담는 것 | 국내 | 해외 | 빌드·런타임에서 |
| :-- | :-- | :-- | :-- | :-- |
| `columns` | 컬럼별 판정 — `missing_reason`·`answer_policy`·`unit`·`trap`·**`kg_entity`** 포인터 | 98컬럼 판정, `kg_entity` 12▶ | 49컬럼, `kg_entity` 6▶ | `kg_entity` → shared 개체 연결, 커버리지 리포트 추적 |
| `product_group` | ETF/ETN 판별 컬럼 | `pd_grp_no` | `pd_grp_no` + `cu_etn_yn` | 규칙 `ETF만` 의 근거 |
| `query_rules` | 질의 조립 규칙 — 조건식 + 근거 + 반례 + 실측 + `triggers` | 44 | 23 | Plan 프롬프트 주입 |
| `answer_rules` | 답변 어투 — 모수 명시, 금지 표현 | 26 (17 §1) / 28▶ | 24 | 조립 단계 |
| `derivation_rules` | 컬럼을 만들지 않고 파생 판정을 규칙으로 | `inverse_direction`·`leverage_multiple` | — | Plan |
| `external_join` | 외부 테이블 조인 계약(키·기준일·커버리지·금지 키) | `ext_etf_holdings` | `ext_ovs_etf_holdings` | Gate 교차질의 판정 |
| `gate_constants` | 상수 컬럼 위반 질의를 HCX 0회로 기각 | `cu_charge_etc_rt`=0 | `pd_trd_ccy`=USD · `pd_mkt_id`=US | Gate |
| `absent_properties` | 속성 부재 선언 → ttl ABSENT + 게이트 어휘 | `hasHoldingsHistory`·`hasNavHistory` | (shared `absent_in` 으로 선언) [리드 검토] | build + Gate |
| `clarify` · `synonyms` · `name_encoding` | 되묻기 · 통칭 · 이름 규약 | 5 / 61 / — (17 §1) | | Ground · Plan |

값 범위(`range`)는 shared 쪽에 있다 — `shared/risk_grade.yaml` 이 `domestic_etfs` 위험등급 1~6 을 선언하고 빌드가 `etf_kr.ttl` 의 `owl:withRestrictions` 로 옮긴다.

### 2.2 첫 판정 목록

| 데이터 사실 | 선언 한 줄 |
| :-- | :-- |
| ETN 545건이 같은 테이블에 있다 | `product_group.column: pd_grp_no` · 규칙 `ETF만: pd_grp_no='ETF'` |
| 총보수 유효 67건, 0·NULL 1,713행 | `columns.cu_charge_rt`: 0 = 미입력 · 규칙 `보수유효: cu_charge_rt > 0 AND pd_grp_no='ETF'` + 모수 67 명시 |
| 인버스 225건 중 음수 부호는 23건 | `derivation_rules.inverse_direction`: 방향은 상품명 '인버스', 배수는 `ABS(cu_lev_fector)` |
| 해외에 위험등급 컬럼이 없다 | `domestic_asymmetry.해외에_없는_것: [위험등급, …]` → ABSENT (§4.2-2) |
| 지수는 `ref_base_index` 904종이 정본, `cu_base_index` 는 95.5% 공백 | `columns.ref_base_index.kg_entity: Index` |
| 수익률 -100 = 거래중단·상폐 110건 | 규칙 `수익률정상: <기간 컬럼> > -100 AND IS NOT NULL` |

이 시점의 yaml 은 "사람이 읽는 EDA 보고서를 기계가 읽는 자리로 옮긴 것"이다(17 §6). 구성종목은 아직 없다.

## 3. 부족한 데이터 → 외부 수집

### 3.1 마스터에 없던 것

주최 공식 예시 5문항 중 3문항("캠브리콘 편입", "에코프로 자회사 편입", "우주항공 테마 연결")이 구성종목을 묻는다. 두 마스터 어디에도 구성종목 컬럼이 없다. 이것이 외부 수집의 유일한 이유다 — ETF 가 외부 수집의 98% 를 차지한다(05 §A).

### 3.2 어디서 어떻게

| | 국내 | 해외 |
| :-- | :-- | :-- |
| 스크립트 | `scripts/fetch_etf_holdings.py` | `scripts/fetch_overseas_holdings.py` |
| 출처 | FunETF 공개 API (`https://www.funetf.co.kr/api/public/product/view/etfpdf`, KRX/코스콤 경유 공시) — 인증 불필요, 0.6초 간격 | SEC EDGAR NPORT-P — `company_tickers_mf.json` 으로 티커→(cik, seriesId) 매핑 후 최신 NPORT-P XML 파싱 |
| 기준일 | 2026-08-21 단일 (마스터 8/22 의 마지막 영업일) | 상품별 `report_date` 8종, 2025-10-31 ~ 2026-06-30 |
| 적재 테이블 | `ext_etf_holdings` | `ext_ovs_etf_holdings` |
| 행수 | 75,859 | 906,848 |
| 커버리지 | ETF 1,160 / 1,235 = **93.9%** (판매중 ETF 는 100%) | ETF 1,356 / 5,972 = **22.7%** (순자산 상위 위주) |
| 유출 가드 | 발행일 ≤ 2026-08-24 (주최 8/24 공지) | 동일 — `AS_OF_LIMIT = "2026-08-24"` |

적재는 `scripts/load_external_holdings.py` 한 벌이 두 테이블을 만든다. 마스터에 섞지 않고 별도 `ext_*` 층에 두는 이유는 주최 데이터와의 충돌을 구조적으로 차단하기 위해서다(16 §2-3).

국내 모수 주의(05 §A): '1,160/1,780 = 65.2%' 로 쓰지 않는다. 안 붙는 620건은 ETN 545(구성종목 개념 없음) + 판매종료 ETF 75 다.

### 3.3 적재 계약 — `external_join`

| | 국내 | 해외 |
| :-- | :-- | :-- |
| 조인 키 | `ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no` | `ext_ovs_etf_holdings.etf_ticker = replace(replace(pd_itm_no,'.K',''),'.O','')` |
| 금지 키 | — | **ISIN 조인 금지** — `FILL.K` 를 ISIN 으로 조인하면 `POWR` 의 구성종목 69행이 붙는다. 오배정 8건 실증 |
| 답변 정책 | '2026-08-21 기준' 병기 · ETN 질의엔 "구성종목 개념이 없는 상품" | 상품별 `report_date` 병기 — 마스터 대비 2~10개월 전, 분기공시라 구조적 |
| Security 노드 | 티커 없는 현금·파생 10,123행은 노드로 만들지 않는다 — 구성종목 수 집계 오염 방지 | 동일 |
| 병합 원칙 | 키 우선순위 티커 > CUSIP > LEI > 이름. **이름만 같으면 병합 금지** (삼성전자 ↔ 삼성전기) | 동일 |

Security 노드의 정본 키는 `ontology/codebooks/security_alias_manual.csv` 에 있다(slug · kr_ticker · dom_ticker · isin · cusip · lei · source · as_of). 삼성전기 행은 "삼성전자와 별개 법인 — 이름 매칭 오탐 회귀 테스트용" 으로 일부러 넣었다.

### 3.4 하지 않은 것과 이유

| 하지 않은 것 | 이유 |
| :-- | :-- |
| 해외 구성종목 전수 수집 | NPORT-P 는 시리즈 단위 분기 공시라 티커 매핑이 안 되는 상품이 많다. 순자산 상위부터 채워 22.7% 에서 멈췄다 |
| 구성종목 시계열 | 수집 기준일 1시점만. `hasHoldingsHistory` ABSENT 로 선언하고 "추이·변동" 질의는 기각 |
| 시세·기준가 시계열 | 마스터가 단일 스냅샷. `hasNavHistory` ABSENT |
| 마스터 값 정정 (지역 오분류 43건 등) | 값을 고치지 않는다(주최 8/24). 규칙으로 우회 (§4.2-6) |

## 4. yaml 재작성 → 완성

### 4.1 외부 데이터가 바꾼 판정

- **Security 가 개체가 됐다.** 마스터만 있을 때 "종목"은 개념이 없었다. `ext_*` 가 들어오자 한 회사가 표기 여러 개로 흩어지는 문제가 생겼고, 그래서 Security 노드와 코드북이 필요해졌다.
- **캠브리콘 사례(17 §3).** 수집물 안에서 같은 회사가 표기 6종(본토 티커 `688256 C1` · 영문 사명 2형 · ISIN `CNE1000041R8` · CUSIP `Y10823105` …)으로 흩어져 있었고, 국내 티커 칸(`dom_ticker`)이 비어 있었다. 종목 9개의 국내 티커를 코드북에 수기 등재(852행 분)해 한 노드로 묶었다. 이름만 같은 것은 묶지 않는다.
- **구성종목 조인 질의의 규칙이 생겼다.** `편입비중상위`("○○를 가장 많이 편입한 ETF" 는 상품명이 아니라 JOIN 후 `weight_pct` 정렬) · 교차질의 프롬프트에 UNION ALL 예시와 "조인키는 짝이 정해져 있다" 경고(ETF-D-029) · 구성종목 근거가 있으면 지역 필터를 겹치지 않는다(9/3, `7a3632a`).
- **KG 는 DB 안에 산다.** 코드북을 고치면 코드 배포와 별개로 DB 배포(`deploy.sh --db-only`)가 필요하다 — 이걸 놓쳐 한 번 더 실패했다(17 §3 ④).

### 4.2 결함 → 선언 (05 §B.2 의 6건)

층 표기: 1층 값 사전(KG alias) · 2층 규칙 문서(query_rules) · 3층 게이트. 17 의 실례 ①②③ 은 각각 -3 · -6 · -2 에 붙는다.

**B.2-1 ETN 545건 혼입 → `disjointWith` + 축 분리** (선언·2층)
국내 545·해외 65건의 ETN 이 같은 테이블에 있다. `fp:ETF owl:disjointWith fp:ETN` 을 선언하되 테이블 클래스를 `fp:ETF` 밑에 두지 않았다 — 두면 ETN 까지 ETF 로 단정하는 모순이 생긴다. 종류 판별은 `pd_grp_no` 가 맡고, Plan 이 `ETF만` 규칙을 항상 주입한다. 실측 ETF-D-025: 규칙 없이 "인버스 ETF 3개" 의 1위가 ETN 이었다(인버스 235건 중 ETN 189건).

**B.2-2 해외 위험등급 컬럼 부재 → ABSENT** (3층) — 17 실례 ③
해외 49컬럼에 위험등급이 없다. 결측이 아니라 구조적 부재다. 한 선언에서 빌드가 `etf_gl.ttl` 의 ABSENT 주석과 Gate 어휘를 같이 만든다. "위험등급 낮은 해외 ETF" → HCX 호출 0회로 기각 + 대체 안내. 답변불가 문항의 "생성하면 감점" 방어이자 비용 방어다.

**B.2-3 총보수 유효 67건, 0=미입력 → `보수유효` + 모수 명시 + 적용 범위** (2층) — 17 실례 ①
0 이 무료인지 미입력인지를 반례로 확정했다(무료 ETF 는 실재하지 않음, ETN 545 전건 NULL, 주최 8/25 답변). 규칙 `보수유효: cu_charge_rt > 0 AND pd_grp_no='ETF'`. 말로 "0이면 미수록이라 말하라" 고 적었을 땐 무시당해(ETF-D-028 "총보수 0.0%") 개별 조회는 `NULLIF(cu_charge_rt,0)` 로 기계 차단했다. 반대 사고도 있었다 — ETF-D-036 에서 이 조건이 개수 집계에 과잉 적용돼 삼성 227→18. "보수를 묻지 않은 질의에는 걸지 않는다" 적용 범위를 규칙에 박았다.

**B.2-4 레버리지 부호 소실 → 이름으로 방향, `ABS()` 배수** (2층)
2차 데이터에서 인버스 상품의 `cu_lev_fector` 가 양수로 바뀌었다. 상품명 '인버스' 225건 vs 음수 23건 — 부호만 믿으면 90% 소실. `derivation_rules.inverse_direction` 이 방향을, `leverage_multiple` 이 배수를 맡는다. 해외도 동형: ETF-O-033 에서 플래그 단독 조건이 진짜 인버스 8건을 놓쳐 플래그+배수+이름 합집합으로 확정. 경고가 yaml 주석(#)에만 있어 프롬프트에 안 실렸던 것이 원인 — 판정 근거는 규칙 본문에 적는다.

**B.2-5 지수 표기 불일치 → `fp:Index` 독립 개체 + closure** (1층)
`S&P 500 TR/CR/NR` 같은 수익률방식·철자 변형을 alias 로 한 노드에 묶었다. `Idx_MSCI_ACWI` 하나에 국내ETF·해외ETF·펀드가 매달린다 — 2.2.5 통합 증거로 리드가 인용. Ground 가 변형 표기를 정본 노드로 접지하고 closure 로 후손을 전개한다.

**B.2-6 지역 삼중 표기 → Region 계층 / 구성종목 부재 → Security 노드** (1층) — 17 실례 ②
한글 11 · 영문 59 · `ref_geo_focus` 23 표기를 계층(국가 ⊂ 권역 ⊂ 글로벌) 노드의 alias 로 통합. 감사(9/2)에서 `ref_geo_focus` 가 0/23 연결인 것을 커버리지 리포트가 잡아 87% 로 복구. 원천 오분류 43건은 값을 고치지 않고 `지역질의_합집합` `(wu_inv_rgn='미국' OR ref_geo_focus='United States of America')` 로 우회(466→494건). Security 는 §3.3·§4.1 참조.

기존 2-4(위험등급 0~6)는 채권 절과 겹치므로 채권 B.2-2 를 참조한다.

### 4.3 개정 이력

| 항목 | 국내 `domestic_etfs.yaml` | 해외 `overseas_etfs.yaml` |
| :-- | :-- | :-- |
| 커밋 수 · 기간 | 74회 · 2026-08-10 ~ | 44회 · 2026-08-11 ~ |
| 줄 수 | 1,274▶ | 768▶ |
| `query_rules` | 44 = always 21 + triggered 23 | 23 = always 17 + triggered 6 |
| `answer_rules` | 26 (17 §1) | 24 |
| `gate_constants` | 1 (`cu_charge_etc_rt`) | 2 (`pd_trd_ccy`·`pd_mkt_id`) |
| ABSENT | 3 (`hasCreditGrade`·`hasHoldingsHistory`·`hasNavHistory`) | 2 (`hasCreditGrade`·`hasRiskGrade`) |

**트리거 선별 주입(2026-08-30 도입).** 규칙 전부를 매 질문에 실으면 근거문서가 11,760자였다. 규칙에 `triggers`(정규식)를 붙여 질문에 걸리는 것만 주입하자 2,780~4,400자로 줄었다(63~76%↓, 커밋 `e58644b` 09-01 ETF 규칙 36개 부여). 항상 실리는 규칙(`ETF만`·`판매중만` 등)은 always 로 남겼다. 트리거 누락은 감사로 잡는다 — 예: 공식 예시 #2 의 '구조·투자전략' 어휘 미주입(`7e5ee36`).

개정의 동력은 서버 오답이다. ETF 트랙 회귀 문항 29건(`ETF_오답기록_2026-09-03.md`) 각각이 규칙·사전·게이트·가드 중 한 곳의 수리로 끝났다. 평가셋은 국내 36·해외 28문항.

## 5. 온톨로지·KG 생성

### 5.1 빌드 절차

```
enums/domestic_etfs.yaml · overseas_etfs.yaml   (컬럼층 — 판정·규칙)
shared/*.yaml 11종 · codebooks/*.csv               (개체층 — 지역·지수·운용사·종목 정본)
        │  python scripts/check_yaml_dupkeys.py     문법·중복
        ▼
python scripts/build_ontology.py   Load → Validate(V1~V7) → Emit → Report
        ├─ ontology/etf_kr.ttl · etf_gl.ttl (+ common.ttl 공통부)   ← 제출물, 손편집 금지
        ├─ DB: kg_node · kg_alias · kg_edge · kg_closure             ← 값 사전
        └─ 커버리지 리포트 (미연결 값 목록)
```

갱신 절차는 17 §5 그대로다: yaml 수정 → `check_yaml_dupkeys.py` → `build_ontology.py` → `pytest tests -q` → `eval/run_gold_check.py` → 커밋 → `deploy/deploy.sh --yaml-only`(enums 만) 또는 `--db-only`(shared·codebooks 를 고쳤을 때 — KG 는 DB 안에 산다).

### 5.2 두 ttl 요지

| | `etf_kr.ttl` (34줄) | `etf_gl.ttl` (21줄) |
| :-- | :-- | :-- |
| 클래스 | `fp:DomesticETF ⊂ fp:Product` ("SQLite 테이블 domestic_etfs") | `fp:OverseasETF ⊂ fp:Product` · `fp:ForeignETF ⊂ fp:ETF` (규격 p.9 예시 클래스, `pd_grp_no='ETF'` 5,972건) |
| 축 분리 | 테이블 클래스는 `fp:ETF` 아래가 아니다. `fp:ETF owl:disjointWith fp:ETN` 은 `common.ttl` | 동일 |
| 속성 | `fp:aum`(KRW, 해외 USD 와 통합 정렬 금지) · `fp:leverageMultiple`(부호 소실 주석) | `fp:expenseRatio`(domain `fp:ETF`, 국내 유효 67건 주석) |
| 값 범위 | `fp:riskGradeValue_DomesticETF` 1~6 (`owl:withRestrictions`, 0등급 없음) | — |
| ABSENT | `hasCreditGrade` · `hasHoldingsHistory`(대체 `ext_etf_holdings`) · `hasNavHistory` | `hasCreditGrade` · `hasRiskGrade`("HCX 호출 0회로 기각") |

ttl 은 스키마다. 인스턴스(어느 표기가 어느 노드인지)는 ttl 에 없고 `kg_*` 테이블에 있다.

### 5.3 KG 값 사전 수치

전체 KG: `kg_node` 41,580 · `kg_alias` 66,592 · `kg_edge` 7,414 · `kg_closure` 9,965 (NUMBERS §3). ETF 두 테이블이 매달리는 개체와 alias 원천 컬럼(05 §B.1·§E.4):

| 개체 | 노드 수(전체) | 국내 컬럼 (값 수) | 해외 컬럼 (값 수) |
| :-- | --: | :-- | :-- |
| Security | 27,996 | `ext_etf_holdings` 10,154 | `ext_ovs_etf_holdings` 31,117 |
| Index | 3,172 | `ref_base_index` 904 / `cu_base_index` 19 | `cu_base_index` 1,848 |
| Organization | 2,527 | `cu_fund_mgmt_co` 99 / `ref_fund_mgmt_co` 29 | `cu_fund_mgmt_co` 382 |
| Region | 60 | `wu_inv_rgn` 11 / `ref_geo_focus` 23 | `wu_inv_rgn` 59 |
| AssetClass | 9 | `wu_inv_ast_type` 9 / `ref_ast_type` 7 | `wu_inv_ast_type` 6 |
| RiskGrade | 7 | `pd_risk_cd`/`pd_risk_nm` 6 | ⊘ |
| Currency | 8 | `pd_curr_cd` 1 | `pd_trd_ccy` 1 |
| CreditGrade | 21 | ⊘ | ⊘ |

노드 수는 4도메인 합계다. ETF 몫만의 노드 수는 NUMBERS 에 없어 적지 않는다.

### 5.4 검증 — V1~V7 중 ETF 에 걸린 것

| 검증 | 잡는 것 | ETF 에서 |
| :-- | :-- | :-- |
| V1 | 죽은 alias — DB distinct 에 없는 값 | 2차 데이터 전환 때 1차 값 alias 정리 [리드 검토] |
| V2 | 한 raw 값이 두 노드에 매달림 | 이름 병합 금지 원칙의 기계 검사 (삼성전자↔삼성전기) [리드 검토] |
| V3 | `kg_entity` 포인터가 shared 에 없음 | 해외 `wu_inv_rgn`·`wu_inv_ast_type`·`pd_trd_ccy` 는 08-25 에 stub 포인터로 등록 |
| V4 | 코드북 `source`·`as_of ≤ 2026-08-24` | `security_alias_manual.csv` 행마다 source·as_of 필수 |
| V6 | ABSENT 선언인데 컬럼이 실재 | 해외 `hasRiskGrade` 선언이 "살아 있는지" 매 빌드 확인 |

검증과 별개로 커버리지 리포트가 "연결 안 된 값" 을 낸다. `ref_geo_focus` 0/23 은 V 위반이 아니라 리포트가 잡은 것이다(§4.2-6).

## 6. 질의 → 답변 — 완성된 구조가 쓰이는 자리

### 6.1 공식 예시 #3 "캠브리콘이 편입된 중국 반도체 ETF를 알려줘"

모델은 복사만 한다 — 값 접지는 그래프, 행 선택은 SQL. 2026-09-03 서버 trace 원문 발췌(05 §C · 10 §4.2):

```
2. [Route] 상품군 — domestic_etfs, overseas_etfs · 근거: 머리명사 ETF · 값 ['반도체', '중국']
3. [Ground] '캠브리콘' → Sec_m_cambricon (Security) [+후손 3] → ticker='688256 C1' · constituent='Cambricon Technologies Corp Ltd' · isin='CNE1000041R8' · cusip='Y10823105' … / '중국' → Region_China [+후손 HongKong] → wu_inv_rgn='중국' · ref_geo_focus='China' …
4. [Gate] 통과 — 교차질의(구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
7. [Guard] ETF 기본모수 주입 — pd_grp_no='ETF' · pd_sale_yn=1 이 SQL 에 없어 주입
9. [Plan] SQL — … JOIN ext_etf_holdings ON etf_code = pd_itm_no WHERE constituent LIKE '%Cambricon%' …
11. [Execute] 9행 조회 → 12. [Answer] 결과 전사 강제
```

| 단계 | 이 질의에서 일어나는 일 | 개입한 층 · 이 문서의 절 |
| :-- | :-- | :-- |
| Route | "ETF" 머리명사 + 값 → 국내·해외 병행 | 라우팅 어휘(빌드 산출) · §5.1 |
| Ground | '캠브리콘' → 표기 6종을 가진 Security 노드 하나. '중국' → Region closure 후손(HongKong)까지 | 1층 값 사전 · §3.3 §4.1 §5.3 |
| Gate | ABSENT·상수 위반 없음 → 통과. 교차질의 판정 + 조인키 짝(`etf_code = pd_itm_no`) 주입 | 3층 + `external_join` · §3.3 |
| Plan | 규칙 트리거 주입(`섹터테마질의`·`편입비중상위` 등) → HCX 가 접지 값을 WHERE 에 복사해 SQL 작성 | 2층 · §4.3 |
| 가드·검증 | ETF 기본모수 주입 · 테이블 화이트리스트 · ext↔마스터 짝 검사 · WHERE 값 사전 대조 | 3층 · §5.3 (값 사전 = 값 검사기) |
| 실행·조립 | JOIN → 9행 → 결과 전사 강제, 기준일 2026-08-21 병기 | `answer_rules`·`external_join.answer_policy` |

**실패 3회가 각각 다른 층의 수리였다** (05 §C): ① 9/1 자산군 컬럼에서 '반도체' 를 찾아 0건 → 2층 `섹터테마질의` ② 값 사전에 국내 티커 표기가 없어 접지 실패 → 1층 코드북 9종목·852행 + DB 배포 ③ 9/3 지역 필터 중첩으로 16→9건, 잘린 5종이 지역 오분류된 진짜 중국 상품 → 2층 "구성종목 근거가 있으면 지역 필터를 겹치지 않는다". 종결(9/4): 14건, 1위 RISE 차이나AI반도체TOP4Plus 편입비중 13.25% 가 정답지와 일치. 4.8초 · HCX 2회(SQL + 답변).

### 6.2 답변불가 예

**게이트 기각 — 해외 위험등급 부재 (17 실례 ③, §4.2-2).** "위험등급 낮은 해외 ETF 알려줘" → Route 가 `overseas_etfs` 단독 → Gate 가 `hasRiskGrade` ABSENT 어휘에 걸려 **HCX 0회** 기각 + "국내 ETF 는 위험등급 조회 가능" 대체 안내. 1층이 비는 순간부터 3층이 받는다 — "없는 것을 찾으러 가지 않는다". 서버 원문 trace 는 05·10 에 없다 [리드 검토].

**정확일치 0 → 되묻기 — "KODEX AI로봇 ETF 정보 알려줘" (10 §4.4).** SQL `TRIM(pd_abrv_nm) = 'KODEX AI로봇'` 0행 → `clarify.존재하지_않는_개체` 가 유사 후보 4건(KODEX AI반도체TOP2플러스 · AI전력핵심설비 · 미국AI전력핵심인프라 · 로봇액티브)을 되묻는다. 부분일치(`KODEX`·`AI`)로 엉뚱한 종목을 답하지 않는다. 2.1초 · HCX 1회(SQL). 되묻기는 답변불가 문항의 정답 형태 중 하나다(주최 8/25).

## 7. 한계와 남은 일 (05 §B.3 + 오답기록)

| # | 한계 | 지금 하는 것 | 남은 일 |
| :-: | :-- | :-- | :-- |
| 1 | 해외 구성종목 22.7% · 보고기준일 8종, 최대 8개월 시차 | 모수와 `report_date` 병기 | 원천(SEC 분기공시)의 한계 — 개선 불가 |
| 2 | 지역 오분류 43건 중 두 컬럼이 모두 틀린 경우(`TIGER 중국소비테마`) | `지역질의_합집합` 으로 복구 가능한 것만 | 값을 고치지 않는 원칙의 비용. 전수조사 문서에 기록 |
| 3 | "레버리지" 경계(배수 절대값 >1)가 인버스2X 98종을 함께 잡음 | 빼지 않고 "인버스가 섞여 있다" 고 밝힘 | 업무 정의 필요 — 미확정 |

## 부록 — 출처 파일 지도

| 이 문서의 절 | 근거 파일 |
| :-- | :-- |
| §0 시기 · §4.3 이력 | `git log -- ontology/enums/*.yaml scripts/fetch_*.py scripts/build_ontology.py` · 커밋 `e58644b`·`7e5ee36` · `ETF_오답기록_2026-09-03.md` · NUMBERS §4 |
| §1 EDA | NUMBERS §1 · `16_ETF_본문원고.md` §1~§2 · `docs/eda/domestic_etfs_notes.md`·`overseas_etfs_notes.md`·`etf_*.md` · `scripts/audit_etf_claims.py` |
| §2 1차 yaml | `ontology/enums/domestic_etfs.yaml`(1,274줄)·`overseas_etfs.yaml`(768줄) · `17_구축과정_ETF.md` §1 · `05_도메인_ETF.md` §E.3 |
| §3 외부 수집 | `scripts/fetch_etf_holdings.py`·`fetch_overseas_holdings.py`·`load_external_holdings.py` docstring · `data/external/holdings/SOURCES.md` · NUMBERS §2 · yaml `external_join` · `ontology/codebooks/security_alias_manual.csv` |
| §4 yaml 완성 | `05` §B.2·§C · `docs/proposal/ontology_engineering_etf.md` §2 · `17` §2~§4 |
| §5 온톨로지·KG | `17` §5 · `scripts/build_ontology.py` · `ontology/etf_kr.ttl`·`etf_gl.ttl` · `05` §B.1·§E · NUMBERS §3 · `04_도메인_채권.md` §B.3(V1~V7 정의) · `ontology/shared/*.yaml` `absent_in` |
| §6 질의·답변 | `10_흐름도_취합.md` §4.2·§4.4 · `05` §C · `17` §4 |
| §7 한계 | `05` §B.3 · `ETF_오답기록_2026-09-03.md` · `overseas_etfs.yaml` `external_join.caveat` |
