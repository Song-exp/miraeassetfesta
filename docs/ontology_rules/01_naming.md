# 규칙 1. 지칭 정리 — 같은 것을 같다고 부르기

> 한 개체가 소스마다 다른 문자열로 나타난다. 문자열을 맞추지 말고 **개체(노드)를 만들어 잇는다.**

> 🔴 생성물입니다. 서술·체크리스트는 `scripts/_ontology_rules_data.py`,
> 목록·수치는 `scripts/gen_ontology_rules_doc.py` 가 yaml·DB 에서 매번 새로 뽑습니다.

| | |
| :-- | :-- |
| 목록 | [규칙 12종 색인](README.md) |
| 컬럼 단위 상세 | [`../data_dictionary/`](../data_dictionary/README.md) |

---

## 1. 데이터가 이랬다

- 발행사 이름이 `(주)` 위치·공백 때문에 갈라진다 — 같은 회사가 둘로 세어진다.
- 신용등급이 `AA` 와 `AA0` 두 표기로 들어온다. 사용자는 'AA' 라고 묻는다.
- 같은 종목이 국내는 티커, 해외는 영문명·CUSIP·LEI, 펀드는 ISIN 으로 온다. 이름으로 매칭하면 **삼성전자 질의에 삼성전기가 섞인다.**

## 2. 그래서 이렇게 정했다

- `normalization.trim_columns` — 비교 전 항상 TRIM (4개 도메인 전부).
- `normalization.grade_suffix` — `AA` → `AA0` 접미사 정규화 후 비교.
- `kg_alias`(노드 ↔ 테이블·컬럼·원시값) 로 **표기가 아니라 개체를 조인**한다. 코드북이 사람이 확정한 정본.

## 3. 전수 인벤토리 — 이 규칙이 실제로 어디에 선언돼 있나

#### (1) `normalization` 의 지칭 정리 항목 — 도메인 전수

| 도메인 | 항목 | 내용 |
| :-- | :-- | :-- |
| 채권 | `trim_columns` | 13개 컬럼 |
| 채권 | `grade_suffix` | 사용자 'AA' → 'AA0' (한국식 중간값 0 표기). 'AA'·'A'·'BBB' 단독 표기는 DB 에 0건 |
| 채권 | `issuer` | '(주)' 위치 앞뒤 제각각 — 정규화 매핑은 kg_organization (§5.1-①) |
| 채권 | `bd_knd_alias` | '통화안정증권'(통칭) → '통화안정채권'(실값 33행) (§5.1-⑧) |
| 국내ETF | `trim_columns` | 9개 컬럼 |
| 해외ETF | `trim_columns` | 6개 컬럼 |
| 해외ETF | `language_note` | 자산군·지역이 영문. 국내ETF(한글)와 교차 시 매핑 테이블 필요 (주식↔Equity, 미국↔United States of America). → 워크샵 §F-2. |
| 펀드 | `trim_columns` | 9개 컬럼 |
| 펀드 | `value_variants` | {'_note': '정확일치 조회 시 누락. 조회 전 정규화하거나 두 표기를 모두 허용할 것', 'zrin_fd_ivst_risk_grd_nm': {'매우 높은 위험': [], '높은 위험': ['높은위험'], '다소 높은 위험': [], '보통 위험': ['보통위험'], '낮은 위험': [], '매우 낮은 위험': []}} |

#### (2) `kg_alias` — 어느 테이블·컬럼이 개체로 이어져 있나

| 테이블 | 컬럼 | alias수 | 노드수 |
| :-- | --: | --: | --: |
| ext_ovs_etf_holdings | holding_name | 13,751 | 8,688 |
| ext_ovs_etf_holdings | cusip | 11,977 | 11,977 |
| public_funds | rptt_ksd_itm_no | 6,883 | 6,883 |
| ext_fund_holdings | holding_nm | 6,497 | 5,316 |
| ext_fund_holdings | isin | 5,474 | 5,470 |
| ext_ovs_etf_holdings | lei | 5,385 | 5,385 |
| ext_etf_holdings | ticker | 3,315 | 3,315 |
| ext_etf_holdings | constituent | 3,290 | 3,290 |
| overseas_etfs | cu_base_index | 1,848 | 1,848 |
| domestic_bonds | pd_pbcm | 1,818 | 1,817 |
| domestic_etfs | ref_base_index | 904 | 904 |
| public_funds | bmrk_nm | 389 | 389 |
| overseas_etfs | cu_fund_mgmt_co | 382 | 381 |
| public_funds | or_co_xtn_itt_cd | 275 | 272 |
| domestic_etfs | cu_fund_mgmt_co | 99 | 39 |

#### (3) 코드북 — 사람이 확정한 정본

| 코드북 | 행 |
| :-- | --: |
| `asset_manager.csv` | 275 |
| `asset_manager_en.csv` | 29 |
| `asset_type_map.csv` | 9 |
| `etf_sector.csv` | 7 |
| `fund_attr_code.csv` | 210 |
| `fund_country_tag.csv` | 17 |
| `fx_rate.csv` | 1 |
| `index_axis_override.csv` | 37 |
| `index_master.csv` | 97 |
| `market.csv` | 6 |
| `public_funds_asset_manager.derived.csv` | 74 |
| `region_map.csv` | 12 |
| `security_alias_manual.csv` | 18 |
| `trustee.csv` | 18 |

## 4. 근거 (라이브 DB 실측)

**발행사 표기 흔들림 — TRIM 하나로 19개가 합쳐진다**

| raw_distinct | trimmed |
| :-- | --: |
| 1,837 | 1,818 |

**신용등급 — `AA` 가 아니라 `AA0` 으로 수록된다**

| 등급 | n |
| :-- | --: |
| AAA | 8,722 |
| AA- | 3,530 |
| AA+ | 2,543 |
| AA0 | 1,241 |

**🔴 이름 LIKE 가 왜 위험한가 — 삼성전자와 삼성전기가 접두사를 공유한다**

| 표기 | n |
| :-- | --: |
| Samsung Electronics Co., Ltd. | 50 |
| Samsung Electronics Co Ltd | 48 |
| SAMSUNG ELECTRO-MECHANICS CO.,LTD | 16 |
| Samsung Electro-Mechanics Co Ltd | 13 |
| SAMSUNG ELECTRONICS CO LTD | 11 |
| Samsung Electronics Co. Ltd. | 11 |
| Samsung Electronics Co Ltd. | 7 |
| SAMSUNG ELECTRO MECHANICS | 5 |

## 5. 안 지키면

‘삼성전자를 보유한 ETF’ 질의에 **삼성전기 보유분이 섞인다.** 발행사 집계는 같은 회사를 둘로 센다.

## 6. 검토 체크리스트

> 전수조사에서 나온 규칙이므로 **규칙 단위로 판정**한다. 각 항목에 결론과 근거를 적고,
> 판정이 바뀌면 `ontology/enums/*.yaml` 또는 `ontology/shared/*.yaml` 을 고친 뒤 재생성한다.

| # | 검토 항목 | 판정 | 근거·조치 |
| :-: | :-- | :-- | :-- |
| 1 | `kg_alias` 가 붙지 않은 이름 컬럼이 남아 있는가 — 특히 해외ETF·펀드의 종목명 계열. |  |  |
| 2 | 코드북의 `status: pending` alias 는 KG 에 들어가지 않는다. **몇 건이고 왜 pending 인지** 확인. |  |  |
| 3 | 종목 정본(`security_alias_manual.csv`) 18종으로 충분한가 — 교차질의에 자주 나올 종목이 빠지지 않았는지. |  |  |
| 4 | `grade_suffix` 외에 접미사 정규화가 필요한 범주형이 더 있는가(운용사 약칭·지수명 등). |  |  |
| 5 | TRIM 만으로 안 합쳐지는 표기(중간 공백·괄호 위치)가 발행사 1,818종 안에 남아 있는지 표본 검사. |  |  |

---

← [색인으로](README.md)
