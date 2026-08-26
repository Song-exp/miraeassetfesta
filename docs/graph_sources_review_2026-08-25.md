# 🕸️ 도메인별 그래프 재료 소스 검토 — 2026-08-25

> 질문: "각 도메인이 그래프(KG)에 낼 수 있는 재료가 무엇이고, 지금 무엇이 연결됐고 무엇이 비어 있나."
> 기준: KG 확장 커밋 `3e62da7`·`2becec1` 이후 상태 (노드 5,088 · alias 5,169 · edge 5,569). 수치는 전부 DB 실측.
> 표기: ✅ 연결됨 · 🟡 재료는 있으나 미연결 · ❌ 개체 자체가 없음 · ⚠️ 규칙 기반(추정)

---

## 0. 한눈에 — 축 × 도메인 연결 현황

| 축(개체) | 국내채권 | 국내ETF | 해외ETF | 공모펀드 | 비고 |
| :-- | :-- | :-- | :-- | :-- | :-- |
| RiskGrade | ✅ 7/7 | ✅ 6/6 | absent(선언) | ✅ 6/6 | 완료 |
| Index | absent(선언) | ✅ 904/905 | ✅ 1,848/1,850 | ✅ 389/389 | 패밀리 70 · 나머지 = 센티넬 |
| Organization(운용사) | — | 🟡 25/100 (`ref_fund_mgmt_co` 29종 미사용) | 🟡 **0/382** | 🟡 67/275 코드(법인명 90종) | 해외 운용사 통째로 비어 있음 |
| Organization(발행사) | ✅ 1,818/1,818 | 🟡 ETN 발행사 11 (`etn_issuers.csv` 있음) | — | 🟡 수탁사 50 코드(`trustee.csv` 17) | |
| Region | absent(선언) | ✅ 11/11 | 🟡 14/59 | 🟡 7/9 + 국가태그 17 미연결 | |
| AssetClass | absent(계층) | 🟡 7/9 ('대체투자'·'기타') | ✅ 6/6 | 🟡 16/18 | |
| Currency | ✅ | ✅ | ✅ | 🟡 2/7 (EUR·JPY·AUD·GBP·SEK) | 5분짜리 |
| **Security(종목)** | — | ❌ | ❌ | ❌ | **개체 없음 — 교차질의의 핵심 축** |
| 상품 간 관계 | — | — | — | ❌ 모자·대표·클래스 | 재료 있음(§4) |
| `kg_entity` 포인터(enums→shared) | 3 | **0** | **0** | **0** | coverage report 가 포인터로 컬럼을 추적하므로 기입 필요 |

---

## 1. 국내채권 — 재료는 풍부, 관계는 미연결

| 소스 | 규모 | 개체/관계 후보 | 상태 |
| :-- | --: | :-- | :-- |
| `pd_pbcm` 발행사 | 1,818 | Organization(issuer) | ✅ 노드 1,817 (`organization_issuer_auto.yaml`) |
| `crd_grd` + `lookups/credit_grade_scale.csv` | 15종 / 서열 19 | CreditGrade 개체 (서열·투자/투기 경계) | 🟡 **enum 화이트리스트로만 존재** — 노드화하면 "AA- 이상" 같은 서열 질의를 closure 로 |
| `bd_knd` + `lookups/collateral_type_map.csv` | 32종 / 42행 | 발행사→담보구분(자산담보부·정부신용·무보증) | 🟡 코드북만, edge 없음 |
| `lookups/issuer_industry_map.csv` (+top200) | 41행 규칙 | 발행사→업종(금융/비금융·공기업) | 🟡 코드북만. 발행사 노드가 생겼으니 `Org —inIndustry→` edge 가능 |
| `lookups/bond_issuer_background.md` | 산은·기은 법정 손실보전 등 | 발행사 속성(정부보증 성격) | 🟡 문서만 |
| `bd_intp_tcd`·`bd_inrt_tcd`·`bd_ofr_tcd`·`std_pd_mcls/scls` | 4·3·2·3/13종 | 분류 축(이표/할인·고정/변동·공모/사모·국공채/특수채/회사채) | 🟡 yaml 판정만 — 얕은 계층 노드로 두면 ETF·펀드의 '채권형' 과 잇는 다리 |
| `name_encoding` 플래그(영구·코코·EB·BW…) | 8종 | 구조 속성 | ✅ yaml 규칙 (그래프 불필요) |

**권고**: ① CreditGrade 노드 19 + `rank` — 서열 질의를 SQL CASE 가 아니라 closure 로. ② 발행사→업종·담보 edge (코드북이 이미 있으니 생성기에 2개 규칙 추가). ③ 국공채/특수채/회사채 를 AssetClass `Bond` 의 하위 노드로 등록해 "채권형 상품 전부(채권+채권ETF+채권펀드)" 교차 가능.

## 2. 국내ETF — 지수는 됐고, 운용사·종목이 남음

| 소스 | 규모 | 개체/관계 후보 | 상태 |
| :-- | --: | :-- | :-- |
| `ref_base_index` | 905 | Index | ✅ 904 (+패밀리) |
| `ref_fund_mgmt_co` (영문 정규 법인명) | 29 | Organization | 🟡 **미사용** — `cu_fund_mgmt_co` 100종 오염 표기 대신 이걸 alias 로 붙이면 국내ETF 운용사 매핑 25→~100% |
| ETN 발행사 (`cu_fund_mgmt_co`, ETN 545) + `lookups/etn_issuers.csv` | 11 / 10 | Organization(issuer, 증권사) | 🟡 코드북 있음, 노드 없음 |
| `ref_ast_type`·`ref_geo_focus` (Lipper 분류) | 7 / 23 | AssetClass·Region 의 제2 근거 | 🟡 `wu_inv_ast_type`·`wu_inv_rgn` 만 매핑. 두 근거 불일치(주최 정답과 69%)는 재검증 §E7 — **둘 다 alias 로 붙이고 충돌은 리포트** |
| `pd_ticker`·`pd_isin_cd`·`pd_ric` | 1,208 | 상품 식별자 (Security 조인 키) | 🟡 ext_* 조인에만 사용 |
| `ext_etf_holdings` (8/21) | 75,859행 · ticker 5,086 · 이름 10,695 | **Security(종목) 개체 + ETF—holds→Security edge** | ❌ 개체 없음 |
| `pd_dvid_pay_months`·`cu_lev_fector`·`cu_strtegy` | — | 속성 | ✅ yaml 규칙 |
| `pd_sect_cd` + `codebooks/etf_sector.csv` | 5 | 섹터 축 | 🟡 코드만, 재검증 §E7 "SingleStock recall 20%" 로 사용 금지 판정 |

**권고**: ① `ref_fund_mgmt_co` alias 추가(생성기 10줄). ② ETN 발행사 노드 11 (`etn_issuers.csv`). ③ Security 개체 — §5.

## 3. 해외ETF — 운용사 382종이 통째로 비어 있음

| 소스 | 규모 | 개체/관계 후보 | 상태 |
| :-- | --: | :-- | :-- |
| `cu_base_index` | 1,850 (센티넬 2 제외) | Index | ✅ 1,848 |
| `cu_fund_mgmt_co` | **382** | Organization | ❌ **0 매핑** — "BlackRock 이 운용하는 국내+해외 ETF" 교차가 막힘. 국내 `ref_fund_mgmt_co` 영문명과 같은 표기 체계(예: 'BlackRock Fund Advisors' vs 'Mirae Asset Global Investments Co Ltd')라 **정규화 규칙 하나로 국내·해외 운용사 통합 가능** |
| `pd_us_cik` | 389 | 운용사 SEC 식별자 | 🟡 노드 키로 쓸 수 있음(운용사 단위, 재검증에서 "CIK 운용사 단위 문제" 확인) |
| `wu_inv_rgn` | 59 | Region | 🟡 14/59 — 'Global Emerging Mkts'·'Asia Pacific ex Japan' 등 45종 미매핑, region.yaml 계층에 붙일 것 |
| `cu_index_repl_mthd`·`cu_inverse_short_yn`·`cu_lev_fector` | — | 속성 | ✅ yaml |
| `ext_ovs_etf_holdings` (1,356 ETF) | 906,848행 · cusip 134k · **LEI 18,609** · 이름 82,550 | **Security 개체** — LEI 가 법인 단위 키, cusip 이 증권 단위 키 | ❌ 개체 없음. 'SAMSUNG ELECTRONICS CO LTD' 와 'SAMSUNG ELECTRO-MECHANICS'(삼성전기) 가 `LIKE '%Samsung Elec%'` 에 같이 걸림 → **이름 매칭은 오탐 — LEI/cusip 노드가 필요한 이유** |
| Index→Region/AssetClass edge | 2,418 / 3,151 | ⚠️ 키워드 규칙 | 733 지수는 지역 없음, Equity 기본값 2,121 — 답변에 "추정" 병기 |

**권고**: ① 운용사 정규화(법인 접미 제거·대소문자) → 국내 29 + 해외 382 통합 Organization 노드. ② 지역 45종 계층 매핑. ③ Security 개체 §5.

## 4. 공모펀드 — 상품 간 관계 재료가 가장 많은데 전부 미사용

| 소스 | 규모 | 개체/관계 후보 | 상태 |
| :-- | --: | :-- | :-- |
| `bmrk_nm` | 389 | Index | ✅ 389 (합성 BM 은 `composite` 표시만) |
| `or_co_xtn_itt_cd` + `codebooks/asset_manager.csv` | 275 코드 / 법인명 90 | Organization | 🟡 67 노드. 나머지 208 은 노드 없음(코드북 status derived/web_confirmed 23 은 있음) |
| `trusc_xtn_itt_cd` + `codebooks/trustee.csv` | 50 / 17 | Organization(수탁사) | 🟡 노드 없음 |
| `zrin_btyp_nm`·`zrin_ptn_nm` | 18 / 102 | AssetClass · 세부유형 | 🟡 18→16 매핑, 102 종 소분류(중국주식·북미주식·일반채권…)는 **Region×AssetClass 를 한 값에 담은 축** — 분해하면 두 edge |
| `prfd_attr_cds` + `codebooks/fund_attr_code.csv` | 210 코드 / 15축 | 태그 개체(테마 N·섹터 O·전략 S·연금 G·지역 W…) | 🟡 코드북 완성, 노드 없음. W 축(세부지역 47종)은 Region 과 직결, N/O 는 ETF 상품명 테마와 다리 |
| `fund_country_tag.csv` | 17 | Region(국가) | 🟡 미연결 |
| `rptt_ksd_itm_no`(대표펀드) / `mtco_itm_no`(펀드묶음) / `std_itm_no` | 6,886 / 14,060 / 18,948 | **상품 간 관계** `FundClass —classOf→ Fund`, `Fund —representedBy→` | ❌ edge 없음 — 재료는 마스터에 그대로 있음 |
| `ext_fund_page.mother_fund_names_raw` | 4,185 | `Fund —feedsInto→ MotherFund` (모자형) | ❌ 텍스트만 |
| `han_clas_*` (클래스 체계) | 195 | 클래스 속성(선취/미징구·온/오프·연금) | ✅ yaml 규칙 (그래프 불필요) |
| `ext_fund_holdings` | 59,206행 · **ISIN 11,893** · 이름 12,582 | Security 개체 — ISIN 이 있어 가장 깨끗한 키 | ❌ 개체 없음 |
| `curr_cd` | 7 | Currency | 🟡 2/7 — EUR·JPY·AUD·GBP·SEK 5종 alias 추가면 끝 |

**권고**: ① 펀드 구조 edge 3종(classOf·representedBy·feedsInto)은 **마스터 컬럼만으로 생성 가능** — 제안서의 "그래프" 논거로 가장 설득력 있음(상품 노드 간 관계). ② 속성코드 15축 중 W(지역)·N(테마)·S(전략) 만 노드화. ③ 수탁사 50 노드.

---

## 5. 🔴 가장 큰 구조적 공백 — Security(종목) 개체

교차질의 예시("삼성전자를 보유한 국내/해외ETF·펀드", "캠브리콘 편입 ETF", "에코프로 자회사 편입 ETF")는 전부 **종목 → 상품** 방향인데, 종목이 개체가 아니라 세 테이블의 문자열이다.

| 소스 | 키 | 삼성전자 표기 | 문제 |
| :-- | :-- | :-- | :-- |
| `ext_etf_holdings` | 6자리 ticker `005930` | '삼성전자' | 깨끗함 |
| `ext_ovs_etf_holdings` | cusip / **LEI** | 'SAMSUNG ELECTRONICS CO LTD', 'SAMSUNG ELECTRONICS GDR REGS' | 이름 LIKE 는 삼성전기('SAMSUNG ELECTRO-MECHANICS')까지 잡음. GDR 은 같은 회사 다른 증권 |
| `ext_fund_holdings` | ISIN | '삼성전자' 외에 'KODEX 삼성전자단일종목레버리지'·'2026-06 삼성전자개별선물' | ETF·선물이 종목명으로 섞임 (`asset_type` 로 분리 가능: 주식 28,201 / 파생 8,607) |

**설계안 (다음 단계)**: `shared/security_auto.yaml` — 노드 키 = ISIN(국내 KR7005930003 ↔ 티커 005930 은 KRX 규칙으로 변환 가능, 해외는 cusip→ISIN 변환 규칙 'US'+cusip+체크디지트, LEI 는 법인 노드로 분리) · alias = {ticker, cusip, LEI, 이름 변형} · edge = `Product —holds→ Security (weight, as_of)` 는 행 수(100만)가 커서 kg_edge 가 아니라 **ext_* 테이블을 edge 테이블로 간주**하고 노드만 만든다. 에코프로 "자회사" 는 `Security —subsidiaryOf→ Security` 수동 코드북(에코프로비엠·에코프로머티 등 소수)으로.

---

## 6. 우선순위 제안 (평가·제안서 영향 순)

| # | 작업 | 효과 | 크기 |
| :-: | :-- | :-- | :-- |
| 1 | **Security 개체 + 이름 정규화** (§5) | 교차질의 3종 예시 전부의 정확도 — 현재 LIKE 매칭의 오탐(삼성전기) 제거 | 1일 |
| 2 | **해외 운용사 382 + 국내 `ref_fund_mgmt_co` 통합 Organization** | "○○ 운용 국내+해외 ETF" 교차 | 반일 |
| 3 | **펀드 구조 edge 3종**(클래스·대표·모자) | 제안서 "그래프" 논거, 클래스 중복 답변 방지 | 반일 |
| 4 | `kg_entity` 포인터를 3개 yaml 에 기입 | coverage report 가 미매핑을 자동 추적 | 1시간 |
| 5 | 잔여 소형: 펀드 Currency 5종 · 해외 Region 45종 · ETN 발행사 11 · 수탁사 50 · CreditGrade 노드 19 · 발행사→업종/담보 edge | 축별 완결 | 각 1시간 |
| 6 | 속성코드 W/N/S 노드화 · 국공채/특수채/회사채 → Bond 하위 | 펀드 태그 질의 · 채권형 교차 | 반일 |

1·2·3 은 전부 `gen_shared_auto.py` 확장으로 재생성 가능하게 만든다. 4 는 yaml 편집(도메인 담당 확인용).
