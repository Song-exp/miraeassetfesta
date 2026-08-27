# D. 온톨로지 관계

> 규칙과 축이 옳게 잡혔는가 — 파생·배타·계층·부재, 그리고 규칙이 실제로 강제되는가.

| | |
| :-- | :-- |
| **왜 보나** | 규칙이 문서에만 있고 기계가 강제하지 않으면 지켜진다는 보장이 없다. |
| **어떻게** | 규칙 원문과 실측 분포를 대조한다. 세부는 `docs/ontology_rules/` 12문서 참조. |
| **담당** | **song**(리드) — 규칙 오탐 표본 확인은 해당 도메인 담당에게 질문 |

> `판정` 칸에 **✅ 이상없음 · ⚠️ 확인필요 · ❌ 고쳐야함** 중 하나를, `근거·조치` 칸에 판단 근거와 고칠 곳(`ontology/enums/*.yaml` 등)을 적습니다.

---

## D-1. 파생 규칙 — 없는 축을 만들어 내는 규칙이 옳은가

| ID | 대상 | 확인할 것 | 자동 수집 근거 | 판정 | 근거·조치 |
| :-: | :-- | :-- | :-- | :-: | :-- |
| D-1-01 | 채권 `axis_derivation.confirmed` | 규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가 | {'couponType': {'rule': 'bd_intp_tcd 직접 매핑 — 이표채→Coupon · 할인채→ZeroCoupon · 복리채→Compound · 단리채→Simple. 고정/변동은 bd_inrt_tcd 직교 축', 'evidence': '✅ 2차 전용 컬럼 (2026-08-25). 1차 종목명·가격구조 추정 폐기'}, 'offeringType': {'rule': 'bd_ofr_tcd 직접 매핑 — 공모/사모', 'evidence': '✅ 2차 전용 컬럼'}, 'riskGrade': {'rule': "pd_risk_gc | ☐ |  |
| D-1-02 | 채권 `axis_derivation.pending_workshop` | 규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가 | {'issuerType': {'rule': 'std_pd_mcls_nm 단독 매핑 (회사채→CorporateBond 등) + pd_no 앞 3자리 보완', 'issue': '소분류 경유 역추적 금지 — 일반사채·특수은행채가 두 대분류에 걸침'}, 'maturityClass': {'rule': '경계값 미정 — remaining_days 기준 (단기 <1y / 중기 1~5y / 장기 >5y 후보)', 'issue': '영구채 266행(mat_dt=콜 개시일)의 처리'}, 'collateralType': {'rule': 'bd_knd | ☐ |  |
| D-1-03 | 국내ETF `derivation_rules.inverse_direction` | 규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가 | {'규칙': "CASE WHEN pd_abrv_nm LIKE '%인버스%' THEN 'Inverse' ELSE 'Long' END", '근거': "🔴 2026-08-25 — cu_lev_fector 부호 소실(columns.cu_lev_fector.trap). 상품명 '인버스' 225건 vs 음수 22건. 음수인데 이름에 '인버스' 없는 행 1건(ETN)은 이름 규칙이 놓치나, 부호 있는 22건은 OR 조건으로 추가 포착 가능: `pd_abrv_nm LIKE '%인버스%' OR cu_lev_fector < 0`.", '축': 'le | ☐ |  |
| D-1-04 | 국내ETF `derivation_rules.leverage_multiple` | 규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가 | {'규칙': 'ABS(cu_lev_fector) — 1.0 Standard · 2.0 2X · 3.0 3X · 0.5/1.5 소수배수(ETN 6건)', '근거': "부호와 무관하게 절댓값은 2차에서도 신뢰 가능 (상품명 '2X'/'레버리지' 314건 중 \\|값\\|=2 가 305건, 3 이 9건).", '축': 'leverageType 의 배수 성분'} | ☐ |  |
| D-1-05 | 국내ETF `axis_derivation.confirmed` | 규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가 | {'strategy': {'accuracy': '100/100', 'rule': "cu_strtegy='액티브' → Active, else Passive"}, 'leverageType': {'accuracy': '100/100 (1차 기준 — 🔴 2차 재검증 필요)', 'rule': '🔴 2026-08-25 개정 — 방향은 derivation_rules.inverse_direction, 배수는 derivation_rules.leverage_multiple 의 조합. (구 규칙 "cu_lev_fector 값매핑 1→Standard, | ☐ |  |
| D-1-06 | 국내ETF `axis_derivation.pending_workshop` | 규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가 | {'_recheck_2026-08-25': '2차 재현(review_recheck §E7): 주최 정답 샘플 100건 중 2차 조인 91건 · ref_ast_type 과 주최 정답 일치 69%(국고채→Equity 는 ref 도 Bond) → 규칙 유도 불가 유지 · 인버스 10/10 양수 배수 = cu_lev_fector 부호 소실 확증 · 섹터코드 8→SingleStock recall 20% 사용 금지 유지', 'assetType': {'accuracy': '92/100', 'issue': '주최 정답이 wu_inv_ast_typ | ☐ |  |
| D-1-07 | 펀드 `derivation_rules.assetClass` | 규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가 | {'축': '무엇에 투자하는가 (하위클래스 결정)', '규칙': '① zrin_btyp_nm(18종, 국내/해외 내장) ② 없으면 종목명 괄호 표기 — (주식…)→Equity, (채권…)→Bond, (주식혼합…)→EquityMixed, (채권혼합…)→BondMixed ③ 없으면 or_attr_desc 폴백', '판정률': '미산출(2차) — zrin_btyp_nm 보유 11,281/23,676 · 판매중 8,551/10,962'} | ☐ |  |
| D-1-08 | 펀드 `derivation_rules.isFundOfFunds` | 규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가 | {'축': '운용 구조 (자산군과 직교)', '규칙': "zrin_attr_nms 태그 'FoFs'(M112) 또는 종목명 '재간접' 또는 or_attr_desc='재간접' (보조: zrin_fd_cmst_rt 가 높음)"} | ☐ |  |
| D-1-09 | 펀드 `derivation_rules.usesDerivatives` | 규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가 | {'축': '파생 활용 (직교)', '규칙': "종목명에 '파생' 또는 or_attr_desc='파생상품'", '해당': '2302 이상(or_attr_desc 기준)'} | ☐ |  |
| D-1-10 | 펀드 `derivation_rules.isMasterFeeder` | 규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가 | {'축': '모자형 구조 (직교)', '규칙': "zrin_attr_nms 태그 '자펀드'(M109) > 종목명 '증권자'/'자투자신탁' 패턴 > 1차 설명서 플래그(external_facts.is_masterfeeder)"} | ☐ |  |
| D-1-11 | 펀드 `derivation_rules.totalFeeApprox` | 규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가 | {'축': '총보수 근사 (%)', '규칙': '(or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r) / 10', '주의': '🔴 기타비용(매매·중개수수료 등) 미포함 — 설명서 TER(ext_fund_page.total_fee_pct)보다 작을 수 있다. 답변에 "보수 합계 기준, 기타비용 제외" 를 명시. 보수_3종전부0 행은 제외.'} | ☐ |  |
| D-1-12 | 펀드 `derivation_rules.prfdAttrTag` | 규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가 | {'축': 'prfd_attr_cds 한 컬럼에 2종류가 섞여 있음 — 형태로 갈라야 한다', '규칙': '① ISO 3자 대문자 → Country (investsIn)  ② <문자><3자리숫자> → FundAttribute (문자=축, 숫자=값)', '판정률': "태그 227종 = 17 + 210 (100%). 1차의 오염 '해외' 태그는 2차에 없음", 'note': '2차에서는 행을 가르지 않는다(목록 컬럼). FundClass 의 다중값 관계로 모델링.'} | ☐ |  |

## D-2. 배타·분리·금지 규칙 — 기계가 강제하는가, 문구뿐인가

| ID | 대상 | 확인할 것 | 자동 수집 근거 | 판정 | 근거·조치 |
| :-: | :-- | :-- | :-- | :-: | :-- |
| D-2-01 | 채권 `영값배제` | `validate_sql` 이 차단하는가, 프롬프트 문구뿐인가 | 수치 정렬·필터 기본 IS NOT NULL AND <> 0 (normalization.zero_as_missing). 예외 컬럼은 zero_is_value. 0 인 행은 '해당 값이 수록되어 있지 않습니다'로 응답 (주최 공지) | ☐ |  |
| D-2-02 | 채권 `과세수익률금지` | `validate_sql` 이 차단하는가, 프롬프트 문구뿐인가 | avg_annual_tax_yield 사용 금지 (전량 0) | ☐ |  |
| D-2-03 | 채권 `더티금지` | `validate_sql` 이 차단하는가, 프롬프트 문구뿐인가 | dirty·ndy_dirty 사용 금지 — 99.0%가 eval_price 동일값(정보량 0). '실제 결제금액' 답변 금지 | ☐ |  |
| D-2-04 | 채권 `등급일사용금지` | `validate_sql` 이 차단하는가, 프롬프트 문구뿐인가 | crd_grd_dt 로 등급 최신성·신선도 판단 금지 — 스키마: '등급 미변경 시 과거 일자로 유지될 수 있음' | ☐ |  |
| D-2-05 | 채권 `이자유형분리` | `validate_sql` 이 차단하는가, 프롬프트 문구뿐인가 | 표면금리 정렬은 bd_intp_tcd·bd_inrt_tcd 로 유형 분리 — 할인채(발행 할인율)·변동금리(스냅샷)·srfc_irt=0(구조) 을 고정 이표채와 한 축에 놓지 말 것 | ☐ |  |
| D-2-06 | 채권 `특수구조제외` | `validate_sql` 이 차단하는가, 프롬프트 문구뿐인가 | 추천·랭킹 질의는 name_encoding 구조 플래그 + bd_ofr_tcd='사모' 기본 제외 + 제외 사실 명시 (제외셋 확정은 워크샵) — 🔴 조회·사실확인 질의에서는 제외하지 않는다. 사모 여부만 답변에 표시한다. | ☐ |  |
| D-2-07 | 채권 `시장집계금지` | `validate_sql` 이 차단하는가, 프롬프트 문구뿐인가 | pd_exg_mkt 단독 group-by 금지 — 구성 효과 교란 (§9.5). 같은 종목이 양 시장에 있을 수 있음 | ☐ |  |
| D-2-08 | 채권 `유동화위험금지` | `validate_sql` 이 차단하는가, 프롬프트 문구뿐인가 | 유동화 = TRIM(bd_knd) IN ('MBS','유동화회사채','Conduit회사채') 3,949 + 코드 밖 SPC 96(발행사명 유동화/신용보증/기술보증 SPC) = 4,045행 (🔴 2026-08-26 정정 — Conduit회사채 1,025행을 bd_knd 코드로 편입. 이전 3,036행은 Conduit 중 16행만 발행사명 패턴으로 회수해 1,009행이 누락돼 있었다). 발행사명으로 위험 판단 금지 — 발행자 = SPC. 조건식: TRIM(bd_knd) IN ('MBS','유동화회사채','Conduit회사채') OR p | ☐ |  |
| D-2-09 | 국내ETF `수치기본배제` | `validate_sql` 이 차단하는가, 프롬프트 문구뿐인가 | <수치 컬럼> IS NOT NULL AND <수치 컬럼> <> 0 — normalization.zero_is_value_columns 는 예외 | ☐ |  |
| D-2-10 | 국내ETF `전부0컬럼금지` | `validate_sql` 이 차단하는가, 프롬프트 문구뿐인가 | cu_charge_etc_rt · pd_dvid_inc_dist · fn_average_maturity · fn_effective_duration · fn_modified_duration 사용 금지 | ☐ |  |
| D-2-11 | 펀드 `ETF제외` | `validate_sql` 이 차단하는가, 프롬프트 문구뿐인가 | itm_nm NOT LIKE '%상장지수%' | ☐ |  |

## D-3. 계층 — 개체에 `parent` 가 있는가

계층이 없으면 ‘아시아 투자 ETF’ 처럼 상위 개념으로 묻는 질의가 0건을 반환한다.

| ID | 대상 | 확인할 것 | 자동 수집 근거 | 판정 | 근거·조치 |
| :-: | :-- | :-- | :-- | :-: | :-- |
| D-3-01 | `AssetClass` | 계층이 필요한 개체인가 — 필요하면 어떤 축으로 세울 것인가 | yaml 노드 9 · KG 9 · `parent` **0** ← 계층 없음 | ☐ |  |
| D-3-02 | `CreditGrade` | 계층이 필요한 개체인가 — 필요하면 어떤 축으로 세울 것인가 | yaml 노드 21 · KG 21 · `parent` **19** | ☐ |  |
| D-3-03 | `Currency` | 계층이 필요한 개체인가 — 필요하면 어떤 축으로 세울 것인가 | yaml 노드 8 · KG 8 · `parent` **0** ← 계층 없음 | ☐ |  |
| D-3-04 | `Index` | 계층이 필요한 개체인가 — 필요하면 어떤 축으로 세울 것인가 | yaml 노드 21 · KG 3,172 · `parent` **4** | ☐ |  |
| D-3-05 | `Organization` | 계층이 필요한 개체인가 — 필요하면 어떤 축으로 세울 것인가 | yaml 노드 64 · KG 2,530 · `parent` **0** ← 계층 없음 | ☐ |  |
| D-3-06 | `Region` | 계층이 필요한 개체인가 — 필요하면 어떤 축으로 세울 것인가 | yaml 노드 59 · KG 59 · `parent` **57** | ☐ |  |
| D-3-07 | `RiskGrade` | 계층이 필요한 개체인가 — 필요하면 어떤 축으로 세울 것인가 | yaml 노드 7 · KG 7 · `parent` **0** ← 계층 없음 | ☐ |  |

## D-4. 부재 선언 — 컬럼이 없다는 사실

| ID | 대상 | 확인할 것 | 자동 수집 근거 | 판정 | 근거·조치 |
| :-: | :-- | :-- | :-- | :-: | :-- |
| D-4-01 | `AssetClass` × 채권 | 게이트가 이 선언으로 실제 기각하는가 · 회귀 테스트가 있는가 | 자산군 컬럼 없음 — 상품 자체가 채권. 클래스 계층(DomesticBond ⊂ Bond)으로 처리 | ☐ |  |
| D-4-02 | `CreditGrade` × 국내ETF | 게이트가 이 선언으로 실제 기각하는가 · 회귀 테스트가 있는가 | 신용등급 컬럼 없음 — ETF 는 발행사 신용등급을 갖지 않음. 위험등급(RiskGrade)과 별개 축 | ☐ |  |
| D-4-03 | `CreditGrade` × 해외ETF | 게이트가 이 선언으로 실제 기각하는가 · 회귀 테스트가 있는가 | 신용등급 컬럼 없음 | ☐ |  |
| D-4-04 | `CreditGrade` × 펀드 | 게이트가 이 선언으로 실제 기각하는가 · 회귀 테스트가 있는가 | 신용등급 컬럼 없음 — 채권형 펀드도 등급은 구성종목 단위(미수록) | ☐ |  |
| D-4-05 | `Index` × 채권 | 게이트가 이 선언으로 실제 기각하는가 · 회귀 테스트가 있는가 | 기초지수 컬럼 없음 — 채권은 지수 추종 상품이 아님. '지수 추종 채권' 질의는 기각 | ☐ |  |
| D-4-06 | `Region` × 채권 | 게이트가 이 선언으로 실제 기각하는가 · 회귀 테스트가 있는가 | 투자지역 컬럼 없음 — PD_CTRY_CD(발행국)는 42,393/42,394가 KR 인 사실상 상수 (enums 판정: kg_entity null) | ☐ |  |
| D-4-07 | `RiskGrade` × 해외ETF | 게이트가 이 선언으로 실제 기각하는가 · 회귀 테스트가 있는가 | 위험등급 컬럼 자체 없음 → '위험등급 낮은 해외ETF' 질의는 HCX 호출 0회로 기각 | ☐ |  |
| D-4-08 | 컬럼 수준 부재 | 해외ETF 기간수익률처럼 **컬럼 자체가 없는** 사실을 어디에 선언할 것인가 | `_absent_columns` 가 도메인 yaml 에 없다 — 개체 수준 `absent_in` 만 존재 | ☐ |  |