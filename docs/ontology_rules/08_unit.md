# 규칙 8. 단위·스케일 — 같은 이름, 다른 눈금

> 컬럼 이름은 ‘보수’ 인데 마스터는 **‰**, 설명서는 **%** 다. 단위를 선언하지 않으면 자릿수가 틀린다.

> 🔴 생성물입니다. 서술·체크리스트는 `scripts/_ontology_rules_data.py`,
> 목록·수치는 `scripts/gen_ontology_rules_doc.py` 가 yaml·DB 에서 매번 새로 뽑습니다.

| | |
| :-- | :-- |
| 목록 | [규칙 12종 색인](README.md) |
| 컬럼 단위 상세 | [`../data_dictionary/`](../data_dictionary/README.md) |

---

## 1. 데이터가 이랬다

- 펀드 보수 컬럼의 단위가 스키마에 없다. 값만 보면 % 인지 ‰ 인지 알 수 없다.
- 국내ETF 분배금 절대액 스케일이 의심스럽다 — 분배수익률과의 산식이 **588/588 정확히 성립**하는데, 그러려면 절대액이 NAV 대비 100배여야 한다.
- 해외ETF 는 USD, 국내는 KRW — 순자산 통합 정렬이 불가능하다.

## 2. 그래서 이렇게 정했다

- `columns.<컬럼>.unit` 으로 단위를 **명시 선언**. 펀드 보수는 `‰`(값÷10 = %).
- 분배금 **절대액은 답변 금지**, 분배수익률(%)·지급월만. 스케일 미확정.
- `통합정렬환율` — USD→KRW 환산 후 정렬 (`fx_rate.csv` 8/21 = 1,384.23).

## 3. 전수 인벤토리 — 이 규칙이 실제로 어디에 선언돼 있나

#### (1) `unit` 선언 — 전수

| 단위 표기 | 컬럼 수 | 컬럼 |
| :-- | --: | :-- |
| `percent` | 32 | 채권.`srfc_irt`, 채권.`exrt_grte_ern_r`, 채권.`exrt_rpy_r`, 채권.`applied_yield`, 채권.`exg_close_yield`, 채권.`buy_yield`, 채권.`after_tax_yield`, 채권.`corp_pretax_yield` … |
| `krw` | 10 | 채권.`isu_bal_amt`, 채권.`bd_tisu_a`, 채권.`eval_price`, 채권.`dirty`, 채권.`exg_close_price`, 채권.`trade_price`, 국내ETF.`du_last_aum`, 국내ETF.`pd_divd_amt_pshr` … |
| `grade` | 3 | 채권.`crd_grd`, 채권.`pd_risk_gcd`, 펀드.`zrin_fd_ivst_risk_gcd` |
| `‰ (값÷10 = %, or_co_rwrd_r 참조)` | 3 | 펀드.`sale_co_rwrd_r`, 펀드.`trusc_rwrd_r`, 펀드.`ofwk_trus_rwrd_r` |
| `yyyymmdd(REAL 저장)` | 2 | 펀드.`fd_last_dstb_actg_bss_dt`, 펀드.`fd_daily_bas_dt` |
| `percent_cumulative` | 2 | 펀드.`fd_yr1_ern_r`, 펀드.`fd_yr3_ern_r` |
| `years` | 1 | 채권.`dur` |
| `days` | 1 | 채권.`remaining_days` |
| `usd` | 1 | 해외ETF.`du_last_aum` |
| `‰ (값÷10 = %) — ext_fund_page 8,925건 대조로 확정 (2026-08-25)` | 1 | 펀드.`or_co_rwrd_r` |
| `krw_per_1000units` | 1 | 펀드.`bns_bpr` |
| `unknown` | 1 | 펀드.`fd_last_dstb_r` |

> 🔴 **같은 단위인데 표기가 2가지다** — `‰ (값÷10 = %) — ext_fund_page 8,925건 대조로 확정 (2026-0`, `‰ (값÷10 = %, or_co_rwrd_r 참조)`. 기계가 단위로 묶으려면 표기를 하나로 통일해야 한다.

> 🟡 `yyyymmdd(REAL 저장)` 는 **단위가 아니라 형식**이다. `unit` 과 `format` 을 분리할지 검토 필요.

#### (2) 단위 관련 query_rules

| 도메인 | 규칙 | 내용 |
| :-- | :-- | :-- |
| 해외ETF | `수치정렬기본` | {col} IS NOT NULL AND {col} <> 0 |
| 해외ETF | `통합정렬환율` | du_last_aum * fx_rate(USD→KRW, fx_rate.csv)   # 개념식 — 실제 조인은 코드북 로더 참조 |

#### (3) 실측 — ‰ 확정의 근거

| 마스터_보수합계 | 설명서_총보수_pct | 배수 | 대조행 |
| :-- | --: | --: | --: |
| 10.942 | 1.094 | 10.0 | 8,998 |

## 4. 근거 (라이브 DB 실측)

🔴 **‰ 의 결정적 증거** — 마스터 보수 합계와 설명서 총보수를 대조하면 정확히 10배

| 마스터_보수합계 | 설명서_총보수_pct | 배수 | 대조행 |
| :-- | --: | --: | --: |
| 10.942 | 1.094 | 10.0 | 8,998 |

**분배금 스케일 의심 — 산식이 588/588 전건 성립한다**

| 산식_성립 |
| :-- |
| 588 |

## 5. 안 지키면

‘보수 0.5% 이하 펀드’ 가 **10배 어긋난 모수**를 반환한다. 분배금 절대액을 답하면 100배 틀린 금액이 나간다.

## 6. 검토 체크리스트

> 전수조사에서 나온 규칙이므로 **규칙 단위로 판정**한다. 각 항목에 결론과 근거를 적고,
> 판정이 바뀌면 `ontology/enums/*.yaml` 또는 `ontology/shared/*.yaml` 을 고친 뒤 재생성한다.

| # | 검토 항목 | 판정 | 근거·조치 |
| :-: | :-- | :-- | :-- |
| 1 | 🔴 `unit` 표기가 통일돼 있지 않다(‰ 두 가지 표기, `yyyymmdd(REAL 저장)` 은 단위가 아니라 형식). **enum 으로 고정**할지 결정. |  |  |
| 2 | `unit` 이 없는 수치 컬럼이 얼마나 되는가 — 단위 미상 컬럼은 비교·정렬 답변에 쓰면 안 된다. |  |  |
| 3 | `percent` 와 `percent_cumulative` 의 차이가 답변에 반영되는가 — ‘3년 수익률 10.5%’ ≠ 연 10.5%. |  |  |
| 4 | 환율이 8/21 단일 시점이다. 해외 순자산 정렬 답변에 환율 기준일을 병기하는가. |  |  |
| 5 | 분배금 절대액 ‘답변 금지’ 를 플래너가 실제로 지키는가 — 컬럼이 SELECT 에 나오지 않도록 가드가 필요한지. |  |  |

---

← [색인으로](README.md)
