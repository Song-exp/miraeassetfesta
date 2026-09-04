# 규칙 6. 파생·유도 — 없는 축을 규칙으로 만든다

> 사용자가 묻는 축(인버스·재간접·모자형·총보수)이 컬럼으로 없다. **다른 컬럼에서 유도**한다.

> 🔴 생성물입니다. 서술·체크리스트는 `scripts/_ontology_rules_data.py`,
> 목록·수치는 `scripts/gen_ontology_rules_doc.py` 가 yaml·DB 에서 매번 새로 뽑습니다.

| | |
| :-- | :-- |
| 목록 | [규칙 12종 색인](README.md) |
| 컬럼 단위 상세 | [`../data_dictionary/`](../data_dictionary/README.md) |

---

## 1. 데이터가 이랬다

- 2차에서 `cu_lev_fector` 의 **인버스 음수 부호가 사라졌다.** 이름에 ‘인버스’ 가 있는 225건 중 음수는 22건뿐.
- ‘총보수’ 컬럼이 없다. 운용·판매·수탁·사무관리 4개를 합쳐야 한다.
- 재간접·모자형 여부가 플래그로 없다. 구성비·태그·종목명에서 판정해야 한다.

## 2. 그래서 이렇게 정했다

- `inverse_direction` — **방향은 상품명 키워드**, 배수는 `ABS(cu_lev_fector)`. 답변에 “상품명 기준” 근거 병기.
- `totalFeeApprox` = (운용+판매+수탁+사무관리)/10 — 기타비용 미포함이라 TER 보다 작다는 것까지 규칙에 명시.
- `isFundOfFunds` · `isMasterFeeder` · `prfdAttrTag`(한 컬럼에 섞인 2종 코드를 **형태로 분리**).

## 3. 전수 인벤토리 — 이 규칙이 실제로 어디에 선언돼 있나

#### (1) 파생 규칙 — 전수 원문

**채권 · `axis_derivation.confirmed`**

| 항목 | 내용 |
| :-- | :-- |
| couponType | {'rule': 'bd_intp_tcd 직접 매핑 — 이표채→Coupon · 할인채→ZeroCoupon · 복리채→Compound · 단리채→Simple. 고정/변동은 bd_inrt_tcd 직교 축', 'evidence': '✅ 2차 전용 컬럼 (2026-08-25). 1차 종목명·가격구조 추정 폐기'} |
| offeringType | {'rule': 'bd_ofr_tcd 직접 매핑 — 공모/사모', 'evidence': '✅ 2차 전용 컬럼'} |
| riskGrade | {'rule': "pd_risk_gcd '11'~'16' → RiskGrade_1~6 · '00' → RiskGrade_0 (shared/risk_grade.yaml)", 'evidence': "✅ 국공채 2,839/2,840 = '16'"} |

**채권 · `axis_derivation.pending_workshop`**

| 항목 | 내용 |
| :-- | :-- |
| issuerType | {'rule': 'std_pd_mcls_nm 단독 매핑 (회사채→CorporateBond 등) + pd_no 앞 3자리 보완', 'issue': '소분류 경유 역추적 금지 — 일반사채·특수은행채가 두 대분류에 걸침'} |
| maturityClass | {'rule': '경계값 미정 — remaining_days 기준 (단기 <1y / 중기 1~5y / 장기 >5y 후보)', 'issue': '영구채 266행(mat_dt=콜 개시일)의 처리'} |
| collateralType | {'rule': 'bd_knd 구조 매핑 (data/external/lookups/collateral_type_map.csv — 1차 기준, 2차 32종으로 재검수 필요)', 'issue': '종목 단위 보증부/담보부 식별 불가 — 무보증 기본값 한계 명시'} |
| issuerCategory | {'rule': 'bd_knd 1차 + 발행사명 키워드 2차 (issuer_industry_map.csv — 1차 8,018사 기준, 2차 1,818사로 축소)', 'issue': '일반회사채 잔여분 키워드 기본값 B급'} |

**국내ETF · `derivation_rules.inverse_direction`**

| 항목 | 내용 |
| :-- | :-- |
| 규칙 | CASE WHEN pd_abrv_nm LIKE '%인버스%' THEN 'Inverse' ELSE 'Long' END |
| 근거 | 🔴 2026-08-25 — cu_lev_fector 부호 소실(columns.cu_lev_fector.trap). 상품명 '인버스' 225건 vs 음수 22건. 음수인데 이름에 '인버스' 없는 행 1건(ETN)은 이름 규칙이 놓치나, 부호 있는 22건은 OR 조건으로 추가 포착 가능: `pd_abrv_nm LIKE '%인버스%' OR cu_lev_fector < 0`. |
| 축 | leverageType 의 방향 성분 |

**국내ETF · `derivation_rules.leverage_multiple`**

| 항목 | 내용 |
| :-- | :-- |
| 규칙 | ABS(cu_lev_fector) — 1.0 Standard · 2.0 2X · 3.0 3X · 0.5/1.5 소수배수(ETN 6건) |
| 근거 | 부호와 무관하게 절댓값은 2차에서도 신뢰 가능 (상품명 '2X'/'레버리지' 314건 중 \|값\|=2 가 305건, 3 이 9건). |
| 축 | leverageType 의 배수 성분 |

**국내ETF · `axis_derivation.confirmed`**

| 항목 | 내용 |
| :-- | :-- |
| strategy | {'accuracy': '100/100', 'rule': "cu_strtegy='액티브' → Active, else Passive"} |
| leverageType | {'accuracy': '100/100 (1차 기준 — 🔴 2차 재검증 필요)', 'rule': '🔴 2026-08-25 개정 — 방향은 derivation_rules.inverse_direction, 배수는 derivation_rules.leverage_multiple 의 조합. (구 규칙 "cu_lev_fector 값매핑 1→Standard, -1→Inverse1X …" 는 부호 소실로 인버스를 전부 Standard/Leveraged 로 오분류한다.)', 'rule_보강': "소수 배수 +0.5(3건 — 약어명 '-0.5X' 인데 부호 소실)·+1.5(3건) 실재 — 전부 ETN. 매핑에 받을 것. 2차 실측 부호 분포: ETF -1.0 1건 / ETN -2.0 16 · -1.0 6 — 나머지 인버스는  |
| distributionType | {'accuracy': '100/100', 'rule': "상품명에 'TR'/'Total Return' → TotalReturn, else Distributing"} |
| replicationMethod | {'accuracy': '99/100', 'rule': "cu_strtegy 실물복제→Physical / 합성복제→Synthetic / 'C'·NULL → 미분류"} |
| region | {'accuracy': '94/100', 'rule': "wu_inv_rgn='국내'→Domestic, else Overseas (+ '미국달러/엔선물' 통화는 Overseas 보정)"} |

**국내ETF · `axis_derivation.pending_workshop`**

| 항목 | 내용 |
| :-- | :-- |
| _recheck_2026-08-25 | 2차 재현(review_recheck §E7): 주최 정답 샘플 100건 중 2차 조인 91건 · ref_ast_type 과 주최 정답 일치 69%(국고채→Equity 는 ref 도 Bond) → 규칙 유도 불가 유지 · 인버스 10/10 양수 배수 = cu_lev_fector 부호 소실 확증 · 섹터코드 8→SingleStock recall 20% 사용 금지 유지 |
| assetType | {'accuracy': '92/100', 'issue': '주최 정답이 wu_inv_ast_type·legacy_leaf 와 상충 (국고채→Equity, MMF/통화 별도). §F-2. 🟢 2차 ref_ast_type(Equity/Bond/Alternatives…)이 제3의 근거 — 셋을 대조해 확정'} |
| underlyingScope | {'accuracy': '87/100', 'issue': '독립축. 상품명 기초자산(대표지수/단일종목/섹터)으로 결정. legacy_leaf 계층으로는 안 나옴. §F-3. 🟢 2차 ref_base_index(905종)로 지수 기반 판정 가능성 재검토'} |

**펀드 · `derivation_rules.assetClass`**

| 항목 | 내용 |
| :-- | :-- |
| 축 | 무엇에 투자하는가 (하위클래스 결정) |
| 규칙 | ① zrin_btyp_nm(18종, 국내/해외 내장) ② 없으면 종목명 괄호 표기 — (주식…)→Equity, (채권…)→Bond, (주식혼합…)→EquityMixed, (채권혼합…)→BondMixed ③ 없으면 or_attr_desc 폴백 |
| 판정률 | 미산출(2차) — zrin_btyp_nm 보유 11,281/23,676 · 판매중 8,551/10,962 |

**펀드 · `derivation_rules.isFundOfFunds`**

| 항목 | 내용 |
| :-- | :-- |
| 축 | 운용 구조 (자산군과 직교) |
| 규칙 | zrin_attr_nms 태그 'FoFs'(M112) 또는 종목명 '재간접' 또는 or_attr_desc='재간접' (보조: zrin_fd_cmst_rt 가 높음) |

**펀드 · `derivation_rules.usesDerivatives`**

| 항목 | 내용 |
| :-- | :-- |
| 축 | 파생 활용 (직교) |
| 규칙 | 종목명에 '파생' 또는 or_attr_desc='파생상품' |
| 해당 | 2302 이상(or_attr_desc 기준) |

**펀드 · `derivation_rules.isMasterFeeder`**

| 항목 | 내용 |
| :-- | :-- |
| 축 | 모자형 구조 (직교) |
| 규칙 | zrin_attr_nms 태그 '자펀드'(M109) > 종목명 '증권자'/'자투자신탁' 패턴 > 1차 설명서 플래그(external_facts.is_masterfeeder) |

**펀드 · `derivation_rules.totalFeeApprox`**

| 항목 | 내용 |
| :-- | :-- |
| 축 | 총보수 근사 (%) |
| 규칙 | (or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r) / 10 |
| 주의 | 🔴 기타비용(매매·중개수수료 등) 미포함 — 설명서 TER(ext_fund_page.total_fee_pct)보다 작을 수 있다. 답변에 "보수 합계 기준, 기타비용 제외" 를 명시. 보수_3종전부0 행은 제외. |

**펀드 · `derivation_rules.prfdAttrTag`**

| 항목 | 내용 |
| :-- | :-- |
| 축 | prfd_attr_cds 한 컬럼에 2종류가 섞여 있음 — 형태로 갈라야 한다 |
| 규칙 | ① ISO 3자 대문자 → Country (investsIn)  ② <문자><3자리숫자> → FundAttribute (문자=축, 숫자=값) |
| 판정률 | 태그 227종 = 17 + 210 (100%). 1차의 오염 '해외' 태그는 2차에 없음 |
| note | 2차에서는 행을 가르지 않는다(목록 컬럼). FundClass 의 다중값 관계로 모델링. |

— 총 **12개 파생 규칙**

#### (2) 실측 — 파생이 실제로 몇 건을 만들어내나

| 판정축 | n |
| :-- | --: |
| 이름에 인버스 | 225 |
| 부호가 음수(신뢰 불가) | 23 |
| 레버리지 ABS>1 | 324 |
| 펀드 재간접 후보(펀드구성비>0) | 7,776 |
| 펀드 총보수 산출 가능 | 8,969 |

## 4. 근거 (라이브 DB 실측)

**🔴 인버스 부호 소실 — 이름과 부호가 어긋난다**

| 이름에_인버스 | 부호가_음수 | 둘_다 |
| :-- | --: | --: |
| 225 | 23 | 22 |

**총보수는 합성 축 — 성분 4개가 따로 있다 (단위 ‰)**

| 운용 | 판매 | 수탁 | 사무관리 |
| :-- | --: | --: | --: |
| 4.749 | 5.392 | 0.341 | 0.157 |

## 5. 안 지키면

부호를 믿으면 **‘인버스 ETF’ 질의가 203건을 놓친다.** 총보수를 성분 하나로 답하면 값이 1/4 로 나온다.

## 6. 검토 체크리스트

> 전수조사에서 나온 규칙이므로 **규칙 단위로 판정**한다. 각 항목에 결론과 근거를 적고,
> 판정이 바뀌면 `ontology/enums/*.yaml` 또는 `ontology/shared/*.yaml` 을 고친 뒤 재생성한다.

| # | 검토 항목 | 판정 | 근거·조치 |
| :-: | :-- | :-- | :-- |
| 1 | `inverse_direction` 이 이름 규칙이라 **오탐·누락**이 있다. ‘인버스’ 없는 인버스 상품, ‘인버스’ 있는 비인버스 상품을 표본 확인. |  |  |
| 2 | `totalFeeApprox` 에 `ofwk_trus_rwrd_r=0`(4,866건) 이 들어간다 — 합산 성분이라 0 을 빼면 안 된다는 판정이 규칙에 명시돼 있는가. |  |  |
| 3 | 해외ETF 에는 파생 규칙이 하나도 없다. 인버스·레버리지 판정을 `cu_inverse_short_yn` 로만 하는데 신뢰 가능한가. |  |  |
| 4 | 채권에 `derivation_rules` 가 없다 — 유동화·영구채·FRN 판정이 `query_rules` 에 흩어져 있다. 옮길지 검토. |  |  |
| 5 | 파생 결과를 답변에 **‘추정’ 으로 표시**하는 규칙이 있는가(edge 와 같은 취급이 필요). |  |  |

---

← [색인으로](README.md)
