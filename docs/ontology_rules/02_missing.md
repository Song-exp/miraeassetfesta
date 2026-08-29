# 규칙 2. 결측 방어 — 비어 있음의 뜻을 가른다

> 주최: 0·결측은 **의도된 값**. 채우지 말고 **왜 비었는지를 선언**한다. 답변 문장이 여기서 갈린다.

> 🔴 생성물입니다. 서술·체크리스트는 `scripts/_ontology_rules_data.py`,
> 목록·수치는 `scripts/gen_ontology_rules_doc.py` 가 yaml·DB 에서 매번 새로 뽑습니다.

| | |
| :-- | :-- |
| 목록 | [규칙 12종 색인](README.md) |
| 컬럼 단위 상세 | [`../data_dictionary/`](../data_dictionary/README.md) |

---

## 1. 데이터가 이랬다

- 채권 판매 조건이 97.1% 비어 있다. '값을 모른다' 가 아니라 **'당사 판매 목록에 없다'** 는 사실이다 — 주어가 시장이 아니라 미래에셋이다.
- 값이 있는데 의미가 없는 칸이 있다(위장결측). 날짜 `0`, 듀레이션 `99`, 대표코드 더미.
- 부재를 특정 값으로 표시한 칸이 있다(센티넬). 수익률 `-100`, 기초지수 문자열 — **`IS NULL` 로는 안 잡힌다.**

## 2. 그래서 이렇게 정했다

- `missing_reason` 분류: `not_applicable` / `missing` / `present`·`none` / `mixed`.
- 분류마다 **답변 문장이 고정**된다 — `not_applicable` 은 “해당 사항이 없습니다”, ❌ “모릅니다” 로 답하면 오답.
- 위장결측은 `dummy_as_missing`·`invalid_values`, 센티넬은 `query_rules.수익률정상`·`기초지수유효` 로 배제.

## 3. 전수 인벤토리 — 이 규칙이 실제로 어디에 선언돼 있나

#### (1) `missing_reason` 분포 — 도메인 × 분류

| 도메인 | `mixed` | `missing` | `none` | `not_applicable` | `present` | `unresolved` | `None` | 계 |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| 채권 | 6 | 14 | 22 | 16 | 0 | 0 | 0 | 58 |
| 국내ETF | 35 | 8 | 5 | 4 | 5 | 0 | 0 | 57 |
| 해외ETF | 18 | 5 | 3 | 0 | 9 | 0 | 2 | 37 |
| 펀드 | 3 | 30 | 20 | 1 | 0 | 6 | 3 | 63 |

> 🔴 **문서화된 4분류 밖의 값이 있다** — `unresolved`, `None`. `None` 은 필드 자체가 비어 있는 것이고, 그 외는 정의되지 않은 분류다. 답변 문장이 분류에서 나오므로 **분류 밖 값은 답변 규칙이 없는 상태**다.

#### (2) `mixed` 판정 62개 중 **값별 분해가 없는 것 56개**

`mixed` 는 '행마다 이유가 다름' 이라는 선언이므로 `missing_semantics` 로 값별 분해가 있어야 답변 문장을 고를 수 있다. 분해가 없으면 **판정만 있고 답변 규칙은 없는 상태**다.

> 🔴 분해 없는 컬럼 56개 — 국내ETF.`pd_ticker`, 국내ETF.`pd_isin_cd`, 국내ETF.`pd_ric`, 국내ETF.`du_last_aum`, 국내ETF.`pd_divd_amt_pshr`, 국내ETF.`pd_divd_amt_ann`, 국내ETF.`pd_dvid_yield`, 국내ETF.`pd_dvid_cycl`, 국내ETF.`pd_dvid_pay_cnt`, 국내ETF.`pd_dvid_pay_months`, 국내ETF.`pd_dvid_nav`, 국내ETF.`pd_dvid_tax_basis`, 국내ETF.`pd_dvid_base_dt`, 국내ETF.`pd_dvid_prc_base_dt`, 국내ETF.`du_chas_errt`, 국내ETF.`du_diff_rt`, 국내ETF.`du_chas_errt_base_dt`, 국내ETF.`du_diff_rt_base_dt`, 국내ETF.`du_nav_base_dt`, 국내ETF.`du_vlty_1y`, 국내ETF.`du_vlty_6m`, 국내ETF.`du_vlty_3m`, 국내ETF.`du_vlty_1m`, 국내ETF.`du_vlty_base_dt`, 국내ETF.`fn_portfolio_dt`, 국내ETF.`fn_base_dt`, 국내ETF.`ref_base_index`, 국내ETF.`ref_base_dt`, 국내ETF.`ref_fund_mgmt_co`, 국내ETF.`ref_ast_type`, 국내ETF.`ref_geo_focus`, 국내ETF.`ru_mkt_price`, 국내ETF.`ru_mkt_volume`, 국내ETF.`cu_lev_fector`, 국내ETF.`cu_strtegy`, 해외ETF.`cu_lev_fector`, 해외ETF.`pd_lstg_dt`, 해외ETF.`cu_strtegy`, 해외ETF.`cu_index_repl_mthd`, 해외ETF.`cu_index_tracking_yn`, 해외ETF.`cu_inverse_short_yn`, 해외ETF.`cu_etn_yn`, 해외ETF.`du_opr`, 해외ETF.`du_hpr`, 해외ETF.`du_lpr`, 해외ETF.`du_bpr`, 해외ETF.`du_clpr`, 해외ETF.`du_vol_1d`, 해외ETF.`pd_isin_cd`, 해외ETF.`pd_us_cik`, 해외ETF.`pd_lipper_id`, 해외ETF.`pd_curr_cd`, 해외ETF.`du_clpr_base_dt`, 펀드.`han_clas_policie

| 도메인 | 컬럼 | 한글명 | missing_semantics |
| :-- | :-- | :-- | :-- |
| 채권 | `srfc_irt` | 표면금리 | {None: "XS 외국발행 1건(XS3067881758 뱅크오브아메리카, 2055년 만기 무이표) — 표면금리·만기일·발행일·통화(curr_cd='000') 미수록. 답변에 사용 불가", 0: 'mixed'} |
| 채권 | `dur` | 듀레이션 | {99: 'sentinel', 0: 'mixed'} |
| 채권 | `cov` | 컨벡시티 | {0: 'mixed'} |
| 채권 | `exg_close_price` | 장내 채권종가 | {0: 'missing'} |
| 채권 | `exg_close_yield` | 장내 종가수익률 | {0: 'missing'} |
| 채권 | `exg_close_price_base_dt` | 장내 종가 기준일 | {'': 'missing'} |

— 총 **6개 컬럼**

#### (3) 위장결측·센티넬 선언

- **채권** `zero_as_missing` — {'기본': '수치 컬럼 정렬·필터는 IS NOT NULL AND <> 0 기본 — 아래 zero_is_value 컬럼만 예외', 'zero_is_value': ['bdbns_abl_chnl_tcd'], 'zero_as_missing_columns': ['exg_close_price', 'exg_close_yield', 'applied_yield', 'isu_dt', 'mat_dt', 'isu_bal_amt', 'bd_tisu_a', 'dur', 'ndy_eval_price', 'ndy_applied_yield', 'avg_annual_tax_yield']}
- **펀드** `dummy_as_missing` — {'_note': '🔴 NULL 만 결측으로 보면 틀린다. 식별 코드의 결측 대부분이 0패딩 더미다. 정규화 없이 조인하면 \'000000000000\' 하나에 1만 행이 뭉치고, LLM 프롬프트에 원값이 닿으면 "등록번호는 000000000000입니다" 라고 답한다 — 환각 감점에 직결된다.', '🔴_화이트리스트_필수': "patterns 를 columns 목록 **밖**의 컬럼에 적용하지 말 것. 고정 자리수 코드에서 '전부 0' 은 흔한 정상값이다 — fd_estb_ctry_cd '000' 23,055 · pfiv_sale_cntl_tcd '00' 22,263 · fd_set_pcd '00' 1,967 은 값이다.", 'patterns': ['^(KR)?0+$', '^(.)\\1+$'], 'columns': ['fss_itm_no', '
- **펀드** `invalid_values` — {'_note': "2차에서 1차의 오염 유래 이탈값 5종('20054.0'·'06'·'해외'·'00080008'·'KRZ50226929C') 전부 소멸. 현재 등재 0건."}
- **펀드** `contaminated_rows` — {'_note': '✅ 2026-08-25 — 감지 조건(mtco_itm_no LIKE \'%"%\' OR itm_no=\'"\') 0행. 1차의 오염 66행/9종목·귀속표는 2차 데이터에 없다. 감지 조건은 재적재 시 재감지용으로 유지한다.', '감지': 'mtco_itm_no LIKE \'%"%\' OR itm_no = \'"\'', '영향_2차': 0}
- **펀드** `zero_as_missing` — {'_note': '🔴 기본 규칙 — 수치 컬럼을 **정렬·필터·집계에 쓸 때는 IS NOT NULL AND <> 0** 을 건다. 개별 조회에서 0 은 "수록되어 있지 않습니다" 로 답한다(값을 고쳐 채우지 말 것). 단 아래 zero_is_value 컬럼은 0 이 실제값이므로 예외. 1차 규칙 fd_nast_suma(0값 294) · 수익률_9기간전부0(69) 은 2차에 해당 행이 0건이라 **삭제**했다.', '보수_3종전부0': {'규칙': 'or_co_rwrd_r=0 AND sale_co_rwrd_r=0 AND trusc_rwrd_r=0 인 행을 보수 결측으로 취급', '영향': '전체 1,081 미만 · 판매중 101 · 판매중·공모 29', 'evidence_grade': 'B', '근거': '운용·판매·수탁이 동시에 0 인 공모

## 4. 근거 (라이브 DB 실측)

**`not_applicable` 의 대표 사례 — 채권 판매 조건 결측은 '진열대에 없다' 는 뜻**

| 전체 | 결측 | pct |
| :-- | --: | --: |
| 21,882 | 21,248 | 97.1 |

**위장결측 — 값은 있는데 의미가 없다**

| 듀레이션99 | 발행일0 | 만기일0 |
| :-- | --: | --: |
| 3 | 25 | 4 |

**센티넬 ① 수익률 -100 — `IS NULL` 로 안 잡힌다**

| du_er_1y가_정확히_마이너스100 |
| :-- |
| 110 |

**센티넬 ② 해외 기초지수 — 문자열로 부재를 표시 (NULL 은 11건뿐)**

| 센티넬 | n |
| :-- | --: |
| not available on Lipper Database | 635 |
| not provided by Management Company | 2,285 |

## 5. 안 지키면

결측을 '모른다' 로 답하면 오답이고, 센티넬을 못 거르면 **수익률 최하위 Top-N 이 전부 상장폐지 종목**으로 채워진다.

## 6. 검토 체크리스트

> 전수조사에서 나온 규칙이므로 **규칙 단위로 판정**한다. 각 항목에 결론과 근거를 적고,
> 판정이 바뀌면 `ontology/enums/*.yaml` 또는 `ontology/shared/*.yaml` 을 고친 뒤 재생성한다.

| # | 검토 항목 | 판정 | 근거·조치 |
| :-: | :-- | :-- | :-- |
| 1 | 🔴 분류 밖 값(`unresolved`·`None`)이 있는 컬럼 — **답변 규칙이 없는 상태**다. 4분류 중 하나로 확정하거나 분류를 늘릴지 결정. |  |  |
| 2 | `mixed` 컬럼에 `missing_semantics` 가 실제로 붙어 있는가. 없으면 분해 불가라 답변이 애매해진다. |  |  |
| 3 | `present`·`none` 판정인데 실측 결측이 있는 컬럼 — `data_dictionary/` 의 ⚠️ 목록과 대조 (총 18건). |  |  |
| 4 | 위장결측 조건식이 2차에서도 유효한가 — 더미 패턴이 `000000000000` 외에 `00`·`00000` 등 길이 변형으로도 있다. |  |  |
| 5 | 센티넬이 더 있는가 — 전부 0 인 컬럼, 특정 상수로 채워진 컬럼을 `auto.yaml` 재생성 후 재확인. |  |  |

---

← [색인으로](README.md)
