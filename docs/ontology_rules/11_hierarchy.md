# 규칙 11. 계층 — ‘미국’ 질의가 ‘북미’ 를 포함하는가

> 개체에 부모를 달고 조상을 **빌드 타임에 전부 펼쳐** 둔다. 런타임 비용 0.

> 🔴 생성물입니다. 서술·체크리스트는 `scripts/_ontology_rules_data.py`,
> 목록·수치는 `scripts/gen_ontology_rules_doc.py` 가 yaml·DB 에서 매번 새로 뽑습니다.

| | |
| :-- | :-- |
| 목록 | [규칙 12종 색인](README.md) |
| 컬럼 단위 상세 | [`../data_dictionary/`](../data_dictionary/README.md) |

---

## 1. 데이터가 이랬다

- 사용자는 ‘아시아 투자 ETF’ 라고 묻는데 데이터에는 ‘한국’·‘중국’ 이 들어 있다.
- 신용등급은 서열이 있는 범주다 — ‘AA- 이상’ 은 문자열 비교로 안 풀린다.

## 2. 그래서 이렇게 정했다

- `shared/<개체>.yaml` 의 `parent` 로 계층 선언 → `kg_closure` 에 **조상 전개**.
- CreditGrade 는 `rank` 와 투자/투기 밴드를 함께 선언해 ‘이상/이하’ 비교가 가능하게.

## 3. 전수 인벤토리 — 이 규칙이 실제로 어디에 선언돼 있나

#### (1) 개체별 계층 선언 — 전수

| 개체 | 노드 | `parent` 있는 노드 | 계층 |
| :-- | --: | --: | :-- |
| `AssetClass` | 9 | 0 | 🔴 **없음** |
| `CreditGrade` | 21 | 19 | ✅ 있음 |
| `Currency` | 8 | 0 | 🔴 **없음** |
| `Index` | 21 | 4 | ✅ 있음 |
| `Organization` | 64 | 0 | 🔴 **없음** |
| `Region` | 60 | 58 | ✅ 있음 |
| `RiskGrade` | 7 | 0 | 🔴 **없음** |

#### (2) 실측 — KG 에 올라간 계층

| 개체 | 노드수 |
| :-- | --: |
| Security | 27,996 |
| Fund | 7,584 |
| Index | 3,172 |
| Organization | 2,527 |
| FundAttribute | 179 |
| Region | 60 |
| CreditGrade | 21 |
| Country | 17 |
| AssetClass | 9 |
| Currency | 8 |
| RiskGrade | 7 |

| kg_closure_행 | 조상노드 | 자손노드 |
| :-- | --: | --: |
| 9,965 | 4,109 | 9,834 |

## 4. 근거 (라이브 DB 실측)

**개체별 노드 수**

| 개체 | 노드수 |
| :-- | --: |
| Security | 27,996 |
| Fund | 7,584 |
| Index | 3,172 |
| Organization | 2,527 |
| FundAttribute | 179 |
| Region | 60 |
| CreditGrade | 21 |
| Country | 17 |
| AssetClass | 9 |
| Currency | 8 |
| RiskGrade | 7 |

**조상 전개 결과 — 런타임 재귀 없이 조회된다**

| kg_closure_행 | 조상노드 | 자손노드 |
| :-- | --: | --: |
| 9,965 | 4,109 | 9,834 |

## 5. 안 지키면

계층이 없으면 ‘아시아’ 질의가 0건을 반환한다. **AssetClass·Currency·RiskGrade 는 아직 `parent` 가 없다.**

## 6. 검토 체크리스트

> 전수조사에서 나온 규칙이므로 **규칙 단위로 판정**한다. 각 항목에 결론과 근거를 적고,
> 판정이 바뀌면 `ontology/enums/*.yaml` 또는 `ontology/shared/*.yaml` 을 고친 뒤 재생성한다.

| # | 검토 항목 | 판정 | 근거·조치 |
| :-: | :-- | :-- | :-- |
| 1 | 🔴 `parent` 없는 개체(AssetClass·Currency·Organization·RiskGrade) 중 계층이 **정말 필요 없는 것**은 무엇인가. AssetClass 는 ‘주식형 ⊃ 국내주식형’ 이 필요해 보인다. |  |  |
| 2 | Organization 계열사 관계(`subsidiaryOf`)가 3건뿐이다 — 운용사 275종에 계열 구조가 있는가. |  |  |
| 3 | Region 계층이 사용자 어휘와 맞는가 — ‘신흥국’·‘선진국’ 같은 축이 있는가. |  |  |
| 4 | CreditGrade `rank` 로 ‘AA- 이상’ 이 실제로 풀리는지 gold SQL 로 확인(OFFICIAL-001). |  |  |
| 5 | Index 패밀리 계층(‘S&P500 계열’)이 어디까지 묶여 있는가. |  |  |

---

← [색인으로](README.md)
