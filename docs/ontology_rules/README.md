# 🧱 온톨로지 규칙 12종 — 규칙별 검토 문서

> 전수조사에서 나온 규칙을 **규칙 하나당 문서 하나**로 갈라 두었다.
> 문서마다 `데이터가 이랬다 → 그래서 이렇게 정했다 → 전수 인벤토리 → 실측 근거 → 안 지키면 → 검토 체크리스트`.
> 3개 도메인(채권 · ETF · 펀드) 합본이며 외부 데이터(`ext_*`)를 포함한다.

| # | 규칙 | 무엇을 막나 | 검토 항목 |
| :-: | :-- | :-- | --: |
| 1 | **[지칭 정리](01_naming.md)** | 같은 것을 같다고 부르기 | 5 |
| 2 | **[결측 방어](02_missing.md)** | 비어 있음의 뜻을 가른다 | 5 |
| 3 | **[외부 데이터 병합](03_external.md)** | 마스터를 고치지 않고 옆에 붙인다 | 5 |
| 4 | **[행 단위(grain)](04_grain.md)** | `COUNT(*)` 는 종목 수가 아니다 | 5 |
| 5 | **[기본 모수](05_population.md)** | 말하지 않은 조건을 고정한다 | 5 |
| 6 | **[파생·유도](06_derivation.md)** | 없는 축을 규칙으로 만든다 | 5 |
| 7 | **[배타·분리](07_disjoint.md)** | 한 축에 놓으면 안 되는 것들 | 5 |
| 8 | **[단위·스케일](08_unit.md)** | 같은 이름, 다른 눈금 | 5 |
| 9 | **[금지 규칙](09_forbid.md)** | 이 컬럼으로는 답하지 마라 | 5 |
| 10 | **[부재 선언](10_absent.md)** | 컬럼이 없다는 사실도 지식이다 | 5 |
| 11 | **[계층](11_hierarchy.md)** | ‘미국’ 질의가 ‘북미’ 를 포함하는가 | 5 |
| 12 | **[기준일·시점](12_asof.md)** | 언제 기준의 사실인가 | 5 |

— 검토 항목 총 **60개**

## 이 문서들을 어떻게 쓰나

| 목적 | 방법 |
| :-- | :-- |
| **검토** | 문서 §6 체크리스트의 `판정`·`근거·조치` 칸을 채운다. 규칙 단위라 담당을 나누기 쉽다 |
| **제안서 §02** | §1~§2(결함→규칙)를 문단으로 풀고 §4 실측 표를 근거로 싣는다 |
| **판정 변경** | `ontology/enums/*.yaml`·`shared/*.yaml` 을 고친 뒤 재생성. yaml 은 `loader.planner_context()` 를 통해 **플래너 프롬프트로 그대로 전달**되므로 답변 동작이 바뀐다 |

## 재생성

```bash
python scripts/gen_ontology_rules_doc.py        # 12개 전부
python scripts/gen_ontology_rules_doc.py 2 8    # 규칙 2·8 만
```

서술·체크리스트는 `scripts/_ontology_rules_data.py`, 인벤토리 추출기는 `scripts/gen_ontology_rules_doc.py` 의 `inv_*` 함수에 있다.

## 규칙 적용의 불균형

규칙은 12종이지만 **4개 도메인에 모두 선언된 최상위 키는 5개뿐**이다(`domain`·`row_grain`·`columns`·`normalization`·`query_rules`).

| 도메인 | `query_rules` | 컬럼 판정 | 도메인 전용 블록 |
| :-- | --: | :-- | :-- |
| 채권 | 20 | 58/58 | `name_encoding`, `clarify`, `axis_derivation`, `workshop` |
| 국내ETF | 18 | 57/98 | `product_group`, `derivation_rules`, `axis_derivation` |
| 해외ETF | 13 | 19/49 | `column_korean_names`, `product_group`, `constant_columns`, `domestic_asymmetry` |
| 펀드 | 14 | 69/75 | `missing_profile`, `entities`, `class_hierarchy`, `axis_mapping`, `derivation_rules`, `attributes`, `cross_domain`, `external_facts` |

**비어 있는 것** — 역질문 규칙(`clarify`)은 채권에만, 교차 도메인 규칙(`cross_domain`)은 펀드에만 있다. `shared/` 개체 7종의 수동 `edges` 는 전부 0 이라 `kg_edge` 는 **전량 `source: rule`(추정)** 이고, 그래서 답변에 “추정” 을 병기한다. AssetClass · Currency · RiskGrade 는 `parent` 가 없어 계층 질의가 안 된다.
