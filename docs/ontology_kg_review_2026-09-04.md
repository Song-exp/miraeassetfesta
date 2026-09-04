# 최종 구현 온톨로지·KG 검토 — 2026-09-04 (1차)

> 대상: `ontology/*.ttl` 5분할 · `ontology/enums|shared|codebooks/*` · DB `kg_*` 4테이블 · `build/viz_kg.json`
> 검토 시점 산출물: ttl `09-03 20:42` · DB `09-03 20:42` · `build_ontology.py --check` **오류 0 · 경고 8**
> 시각 자료: [값 사전 KG 그래프 탐색기](https://claude.ai/code/artifact/82e62d26-c0f2-451f-8601-9d66c51e8f68) — 이 검토 결과가 하단 '구현 실측' 절에 반영돼 있다. 원본 `docs/viz/ontology_graph_ui.html`
> 이 문서는 **구현물 정합 검토**다. 런타임 답변 품질은 `funds_test_result_2026-09-04.md` 를 본다.

---

## 0. 한 줄

**파이프라인은 건강하다**(yaml→ttl+KG 단일 원천, 검증 오류 0, 멱등 재생성). 문제는 **온톨로지가 선언한 것과 KG가 담은 것이 갈린다**는 점이다 — ObjectProperty 16종 중 실제 트리플이 있는 건 4종이고, 노드 41,580개 중 **36,678개(88%)가 엣지 하나 없는 고립 노드**다.

---

## 1. 구현 현황 (사실)

### 1-1. 산출물

| 파일 | 줄 수 | 내용 |
| :-- | --: | :-- |
| `common.ttl` | 4.9MB | owl:Class **14** · ObjectProperty **16** · DatatypeProperty **1** · 개체 인스턴스 **42,052** |
| `fund_pub.ttl` | **34** | PublicFund 클래스 · navTotal · riskGradeValue 범위 · ABSENT 4종 |
| `bond_kr.ttl` | 36 | |
| `etf_kr.ttl` | 34 | |
| `etf_gl.ttl` | 21 | |

### 1-2. KG 테이블

| 테이블 | 행 수 |
| :-- | --: |
| `kg_node` | 41,580 |
| `kg_alias` | 66,592 |
| `kg_edge` | **7,414** |
| `kg_closure` | 9,965 |

노드 타입: Security 27,996 · Fund 7,584 · Index 3,172 · Organization 2,527 · FundAttribute 179 · Region 60 · CreditGrade 21 · Country 17 · AssetClass 9 · Currency 8 · RiskGrade 7

---

## 2. 🔴 F1 — 선언한 속성 16종 중 14종이 트리플 0

`common.ttl` 이 `owl:ObjectProperty` 로 선언한 것과, 실제 인스턴스 트리플이 존재하는 것이 갈린다.

| 선언된 속성 | 실제 트리플 |
| :-- | --: |
| `hasAssetClass` | 3,172 ✅ |
| `successor` | 1 (프랭클린 → 우리자산운용) |
| `manages` · `issues` · `isHeldBy` · `hasCreditGrade` · `hasCurrency` · `hasAttribute` · `investsInCountry` · `belongsToFund` · `tracksIndex` · `hasManager` · `hasIssuer` · `hasRegion` · `hasRiskGrade` · `holds` — **14종** | **0** |

⚠️ `hasManager`·`holds` 등이 파일에 2~3회 등장하지만 **전부 `owl:inverseOf` 상호참조**다(예: `fp:manages ... owl:inverseOf fp:hasManager`). 인스턴스 트리플은 하나도 없다.

반대 방향의 불일치도 있다 — **실제로 쓰이는데 선언이 없는 술어 3종**:

| 술어 | 트리플 | `owl:ObjectProperty` 선언 |
| :-- | --: | :-- |
| `coversRegion` | 2,535 | ❌ 없음 (선언된 건 `hasRegion`) |
| `feedsInto` | 1,704 | ❌ 없음 |
| `subsidiaryOf` | 3 | ❌ 없음 |

**왜 문제인가.** RDF 도구로 열면 미선언 술어가 그대로 통과하긴 하나, 심사가 `.ttl` 을 스키마로 읽으면 *"선언한 관계를 하나도 안 채웠다"* 로 보인다. 특히 `hasManager`(운용사)·`holds`(보유종목)·`hasRiskGrade`(위험등급)는 이 과제의 핵심 축이고 데이터가 **DB에 다 있는데** 트리플로 안 나와 있다.

**고칠 자리** — 둘 중 하나. (a) `build_ontology.py` 가 `coversRegion`/`feedsInto`/`subsidiaryOf` 를 선언에 추가하고, 채울 수 있는 관계(hasManager·hasRiskGrade·holds·belongsToFund)를 실제로 emit 한다. (b) 채우지 않을 속성은 **선언에서 뺀다**. 지금처럼 선언만 남기는 게 가장 나쁘다.

---

## 3. 🔴 F2 — 노드 88%가 고립

| 타입 | 전체 | 엣지 있음 | **고립** |
| :-- | --: | --: | --: |
| Security | 27,996 | 4 | **27,992** |
| Fund | 7,584 | 1,682 | **5,902** |
| Organization | 2,527 | 0 | **2,527** |
| FundAttribute | 179 | 0 | 179 |
| Region | 60 | 35 | 25 |
| CreditGrade | 21 | 0 | 21 |
| Country | 17 | 0 | 17 |
| Currency | 8 | 0 | 8 |
| RiskGrade | 7 | 0 | 7 |
| Index | 3,172 | 3,172 | 0 |
| AssetClass | 9 | 8 | 1 |
| **합** | **41,580** | 4,902 | **36,678 (88%)** |

엣지가 붙은 건 사실상 **Index→AssetClass/Region 분류 트리**와 **모자형 체인(Fund→Fund feedsInto)** 둘뿐이다.

공모펀드 도메인 문서(`공모펀드_도메인.pdf`)가 절을 할애해 설명한 관계가 KG에 **관계로는 없다**:

| PDF 절 | 관계 | KG 상태 |
| :-- | :-- | :-- |
| §1.2 역할 분리 | Fund → Organization (운용사) | ❌ alias 만 (`or_co_xtn_itt_cd` 274건) |
| §1.2 역할 분리 | Fund → Organization (수탁사) | ❌ alias 만 (`trusc_xtn_itt_cd` 48건) |
| §3.1 클래스 | Fund ↔ Fund (같은 펀드의 형제 클래스) | ❌ `rptt_ksd_itm_no` alias 6,867건으로만 |
| §3.2 모자형 | Fund → Fund (자→모) | ✅ `feedsInto` 1,704 |
| §2.5 위험등급 | Fund → RiskGrade | ❌ RiskGrade 노드 7개 전부 고립 |
| §2.1 자산군 | Fund → AssetClass | ❌ (Index 만 연결됨) |
| §2.4 투자지역 | Fund → Region/Country | ❌ Country 17개 전부 고립 |
| — | Fund → Security (보유종목) | ❌ Security 27,996 중 4개만 |

**변호 논거는 있다.** `PROJECT.md` §5 가 *"KG를 별도 엔진이 아니라 SQLite 매핑 테이블로 두기로 했다"* 고 명시했고, 실제 설계 의도는 **질의 표기 → DB 값 사전**이다. 그 목적에는 `kg_alias` 66,592건이 잘 작동하고 있다(런타임 `[Ground] KG 개체 매핑`).

**그래도 문제인 이유** — 과제 심사 기준이 *"온톨로지와 지식 그래프로 정합성·신뢰성을 보장"*(PROJECT.md 11행)이고 기술제안서 40점이 **온톨로지 설계 의도**를 본다. "노드는 4만인데 관계는 4종" 은 설명이 필요한 숫자다.

---

## 4. 🟡 F3 — 런타임은 엣지의 0.04%만 읽는다

`src/runtime/loader.py:295` 가 적재하는 엣지는 이것뿐이다:

```python
"select src_id, dst_id from kg_edge where predicate = 'subsidiaryOf'"
```

**7,414 엣지 중 3건**만 런타임 컨텍스트에 올라온다. `hasAssetClass` 3,172 · `coversRegion` 2,535 · `feedsInto` 1,704 는 **적재조차 되지 않는다.**

`kg_closure`(9,965)는 읽고 쓰며(`expand_node`), 이게 실질적인 계층 확장 경로다.

→ 즉 지금 KG의 기능적 실체는 **`kg_alias` + `kg_closure`** 두 테이블이고, `kg_edge` 는 사실상 산출물로만 존재한다.

**고칠 자리** — `feedsInto` 는 이미 답변 가치가 증명됐다(오늘 `KG-010` "모펀드는 뭐야?" ✅ 통과 — 다만 그건 `ext_fund_page.mother_fund_names_raw` 로 답한 것이지 엣지로 답한 게 아니다). 엣지를 읽어 답하는 경로를 하나라도 만들면 "KG가 답에 쓰인다"를 실증할 수 있다.

---

## 5. 🟡 F4 — `build/viz_kg.json`·`kg.html` 이 9일 낡았다

| 파일 | 시각 |
| :-- | :-- |
| `ontology/*.ttl` | 09-03 20:42 |
| `data/financial_products.db` | 09-03 20:42 |
| `build/viz_kg.json` | **08-26 23:02** |
| `build/kg.html` | **08-26 23:09** |

`viz_kg.json` 헤더가 `nodes: 39,677 · edges: 7,414 · asOf 2026-08-22` 인데 현재 DB는 **41,580 노드**다. 시각화가 제출물에 들어간다면 1,903 노드가 빠진 그림이다. 재생성 필요.

---

## 6. 🟡 F5 — 커버리지 리포트의 오탐 (조합 컬럼)

`data/kg_coverage_report.md`:

```
## FundAttribute
- public_funds.prfd_attr_cds : 179/8926 매핑 →
    - 미매핑 'C103,D102,V101,C101'  (73행)
```

`prfd_attr_cds` 는 **쉼표 구분 목록 컬럼**인데 리포트가 조합 문자열 통째로 distinct 를 세고 있다. "8,926종 중 179종 매핑" 은 실제 커버리지가 아니라 **조합의 가짓수**다. `Country` 축도 같은 컬럼에서 같은 오탐(17/8926)이 난다.

리포트가 다음 EDA 우선순위를 정하는 자료(`build_ontology.py` [4 Report])이므로, 이 두 줄이 **실제로는 잘 덮인 축을 최악의 미매핑으로 보이게** 한다. 태그 단위로 쪼개 세야 한다.

---

## 7. ✅ 잘 되어 있는 것

- **단일 원천 원칙이 지켜진다.** ttl·KG 둘 다 생성물이고 헤더에 `DO NOT EDIT` 이 박혀 있다. 손으로 고친 흔적 없음.
- **검증이 실제로 막는다.** `[2 Validate]` 가 죽은 alias·raw 충돌·깨진 포인터를 잡고 실패 시 산출물을 안 만든다. 현재 오류 0.
- **경고 8건은 전부 의도된 것** — 채권 신용등급 5종·통화 3종이 1차 데이터엔 있고 2차엔 없어 `pending` 으로 보류 중. `domestic_bonds.query_rules.외화채없음` 과 정합하며 사유가 기록돼 있다.
- **ABSENT 선언이 실제로 작동한다.** `fund_pub.ttl` 의 4종(`hasCreditGrade`·`hasUnitsOutstanding`·`hasFundManager`·`hasNavHistory`)이 오늘 테스트에서 **4/4 통과**했다(`FND-R01`·`KG-027`·`X23`·`X24`). 온톨로지 선언 → 게이트 → 답변까지 이어지는 유일한 완결 경로다.
- **AssetClass·CreditGrade·Currency 매핑 100%** (`zrin_btyp_nm` 18/18 · `crd_grd` 15/15 · `curr_cd` 7/7).

---

## 8. 오늘 런타임 테스트와 겹치는 지점

`funds_test_result_2026-09-04.md` 의 결함 8개 중 **온톨로지 쪽에서 고칠 것**:

| 런타임 결함 | 온톨로지 조치 |
| :-- | :-- |
| `OFFICIAL-002` 투자전략 환각 | `absent_properties` 에 `hasInvestmentStrategy` 추가 — §7의 ABSENT 4종이 4/4 통과했으므로 **같은 메커니즘에 한 줄** |
| `DOM-12` 전문투자자 27개 오답 | `query_rules.전문투자자코드금지` 가 yaml 에 있는데 안 지켜졌다. 규칙 → `enforce` 슬롯 이관 후보 |
| `DOM-09` 설립국가↔투자지역 혼동 | `fd_estb_ctry_cd` 와 `fd_ivst_rgn_desc` 가 **둘 다 Country/Region 축으로 매핑**돼 구분 신호가 없다. 축 분리 선언 필요 |
| `Z10` 인도주식 유형 | `zrin_ptn_nm`(세부유형) **85개 값 전부 KG alias 미등록** — 아래 F6 |

---

## 8-1. 🔴 F6 — 세부유형 축 `zrin_ptn_nm` 85종이 KG에 통째로 빠져 있다

`public_funds` 의 KG alias 는 10개 컬럼에 붙어 있는데 `zrin_ptn_nm` 이 **없다**.

| 컬럼 | 판매중·공모 distinct | KG alias |
| :-- | --: | --: |
| `zrin_btyp_nm` (대유형: 주식형·해외주식형 …) | 18 | **18** ✅ |
| `zrin_ptn_nm` (세부유형: 인도주식·중국주식·베트남주식 …) | **85** | **0** ❌ |

결과를 실측으로 확인했다 — `Z10`(인도주식)·`KG-012`(중국주식) **두 문항 모두** Ground 가 같은 줄을 냈다:

```
[Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
```

즉 세부유형 질의는 **전적으로 모델의 추측에 의존한다.** `KG-012` 는 맞게 찍었고(205/522 ✅) `Z10` 은 `zrin_btyp_nm='인도주식형'` 이라는 없는 값을 만들어 실패했다(❌). 같은 축, 같은 Ground 결과, 갈린 답 — **비결정이다.**

`zrin_btyp_nm` 18종은 매핑돼 있으니 파이프라인이 이 축을 못 다루는 게 아니라 **이 컬럼만 빠진 것**이다. `ontology/shared/` 에 세부유형 축을 추가하면 85종이 alias 로 들어가고, Ground 가 '인도주식' 을 실재 값으로 확정해 준다. F1~F5 중 **런타임 정답률에 가장 직접 닿는 항목**이다.

---

## 9. 다음 검토 (아직 안 본 것)

1. `ontology/shared/*_auto.yaml` 6종(총 35만 줄) — 자동 생성분의 라벨 품질·중복
2. `kg_closure` 9,965행의 정합 — 정본 노드 계층이 실제로 맞는지
3. `common.ttl` 42,052 개체의 라벨 3종(`label_ko`/`label_en`/`label_official`) 결측률
4. `bond_kr`·`etf_kr`·`etf_gl` 도메인 3종 — 오늘은 공모펀드 축으로만 봤다
5. 제출 규격 §5 대비 최종 점검 (파일명·네임스페이스 `fp: <http://mafest.ai/product#>`)
