# 🕸️ 온톨로지·KG 구축 지시서 — 워크샵(8/17) → 수렴 완료(8/21)

> **작성 2026-08-17 · 마감 2026-09-06 (D-20) · 대상: 3인 전원**
>
> 앞 지시서 → `docs/NEXT_STEPS.md` (**yaml 을 만드는 단계** — 이 문서는 그 다음입니다)
> 설계 근거 전체 → `docs/superpowers/specs/2026-08-12-ontology-design-and-roadmap.md`
>
> **이 문서가 답하는 것 3가지**
> ① 각자 만들어 온 yaml 을 **어떻게 합치나**
> ② **무엇이 `.ttl` 로 가고 무엇이 KG 로 가나**
> ③ 8/21까지 **누가 무엇을 하나**

---

## 0. 오늘 회의 3줄 요약

1. **컬럼 층은 규격대로 잘 왔습니다.** 비어 있는 건 **테이블을 가로지르는 층**입니다 — 규격에 있는 `kg_entity`·`layer` 필드가 **전 파일에서 0건**이고, 개체 층 블록은 애초에 규격이 없어서 펀드 파일에만 있습니다.
2. 그래서 합치는 방식은 **"각자 파일을 이어붙이기"가 아니라 "횡단 층을 새로 만들기"** 입니다 → `ontology/shared/<entity>.yaml` 6개. 이게 앞으로 5일 노동량의 대부분입니다.
3. `.ttl` 과 KG 는 **손으로 쓰지 않습니다.** yaml 을 원천으로 두고 `scripts/build_ontology.py` 가 생성합니다.

---

## 1. 지금 상태 — 각자 해온 것

| 담당 | 테이블 | `enums/*.yaml` | 질의 10문항 | 코드북 |
| :--- | :--- | :--- | :--- | :--- |
| **seohynun** | 국내채권 | 🔴 **없음** | 🔴 없음 | — |
| **LEEbyeoungchul** | 국내ETF | ✅ 180줄 | ✅ `questions_domestic_etfs.jsonl` | 🔴 **미착수** (`ontology/codebooks/` 디렉터리 없음) |
| | 해외ETF | ✅ 115줄 | ✅ `questions_overseas_etfs.jsonl` | |
| **Song-exp** | 공모펀드 | ✅ 659줄 (+개체 블록 6종) | 🔴 없음 | — |

**품질은 좋습니다.** `missing_reason` · `answer_policy` · `note`(건수 포함) · `unit` 이 규격대로 채워져 있고, 펀드 쪽은 `evidence_grade` 까지 붙어 있습니다.

### 1.1 🔴 합치려고 보니 드러난 빈칸 — 두 개

```
① 규격에 있는데 아무도 안 채운 필드
     kg_entity   전 파일 0건     ← "이 컬럼 값이 KG 개체가 된다" 는 표시
     layer       전 파일 0건     ← 단위·방향·개념 (다른 테이블과 비교 가능한가)

② 규격에 아예 없던 층
     entities · class_hierarchy · axis_mapping · cross_domain
       → public_funds.yaml 에만 있음 (규격 외 자발적 추가)
```

> 🔑 **누구의 잘못도 아닙니다.** `NEXT_STEPS.md` §5.1 규격이 **컬럼 층까지만** 정의돼 있었습니다.
> 컬럼 층은 각자 자기 테이블 안에서 끝나지만, **온톨로지의 본체는 테이블을 가로지르는 개체 층**입니다.
> 각자 작업은 규격대로 끝났는데 합치는 자리에 빈칸이 남은 이유가 이것입니다.

**따라서 오늘 할 일은 "제출물 검수"가 아니라 "빠진 층을 함께 만들기"입니다.**

---

## 2. 합치기 — 파일을 어떻게 나눌 것인가

### 2.1 문제 — 공유 개체는 횡단인데 파일은 담당자별입니다

`Organization` 하나가 4개 테이블 5개 컬럼에 흩어져 있습니다.

```
삼성자산운용  ─┬─ domestic_etfs.cu_fund_mgmt_co   = '삼성'
               ├─ overseas_etfs.cu_fund_mgmt_co   = 'Samsung Asset Management'
               ├─ public_funds.or_co_xtn_itt_cd   = '00040010'
               └─ domestic_bonds.PD_PBCM          = '삼성증권(주)'
```

담당자별 파일에 각자 적으면 **같은 개체가 4곳에 쪼개지고**, 넷을 잇는 정보(= 정확히 우리가 필요한 그것)는 어느 파일에도 안 남습니다.

### 2.2 채택 — 2층 구조

```
ontology/
├─ enums/<domain>.yaml      ← 컬럼 층 · 담당자별 · 이미 있음
│                              결측 판정 · 센티넬 · query_rules · answer_policy
│                              "이 테이블을 어떻게 다룰까"
│
├─ shared/<entity>.yaml     ← 🆕 개체 층 · 횡단 · 워크샵에서 함께 만듦
│                              organization / index / region
│                              asset_class / risk_grade / currency
│                              "여러 테이블의 이 값들이 사실 같은 것이다"
│
└─ codebooks/*.csv          ← 외부 수집 · 코드↔이름 (source · as_of 필수)
```

**원칙: 자기 테이블 안에서 끝나면 `enums/`, 테이블을 가로지르면 `shared/`.**

### 2.3 둘을 잇는 것은 `kg_entity` 한 줄

```yaml
# ontology/enums/domestic_bonds.yaml   ← 담당자가 채움
PD_RISK_GCD:
  korean_name: 위험등급코드
  unit: grade
  layer:
    scale: "0~6 (정수)"
    direction: "낮을수록 위험 (1=매우높은위험, 6=매우낮은위험)"
  kg_entity: RiskGrade          # ← 이 한 줄이 shared/risk_grade.yaml 을 가리킴
```

```yaml
# ontology/shared/risk_grade.yaml     ← 워크샵에서 함께 만듦
entity: RiskGrade
nodes:
  RiskGrade_1:
    label_ko: 매우 높은 위험
    aliases:
      - {table: domestic_bonds, column: PD_RISK_GCD,            raw: 1}
      - {table: domestic_etfs,  column: pd_risk_cd,             raw: "PD_RISK_GCD_11"}
      - {table: public_funds,   column: zrin_fd_ivst_risk_gcd,  raw: 1.0}
  RiskGrade_0:
    label_ko: 미분류
    note: 🔴 채권 58건에만 존재 — 워크샵 확정 필요
    aliases:
      - {table: domestic_bonds, column: PD_RISK_GCD, raw: 0}
absent_in:
  overseas_etfs: 컬럼 자체 없음 → "해외ETF에는 위험등급이 부여되지 않습니다"
```

> 🔴 **`absent_in` 을 빼먹지 마세요.** 이게 `.ttl` 의 **속성 부재**가 되고, *"위험등급 낮은 해외ETF"* 를 **HCX 호출 0회로 기각**하는 근거입니다. 없다는 사실도 데이터입니다.

### 2.4 도메인 전용 개체는 도메인 파일에 남깁니다

`public_funds.yaml` 의 개체 블록을 전부 `shared/` 로 올리는 게 아닙니다.

| 개체 | 어디로 | 왜 |
| :--- | :--- | :--- |
| `AssetManager`(67) · `Custodian`(18) · `Benchmark`(391) · `Country`(17) | 🔼 **`shared/`** | 다른 테이블에도 같은 개념이 있음 → Organization / Index / Region 으로 흡수 |
| `FundClass` · `Fund` · `ShareClass` · `FundAttribute`(210, 15축) | ⬜ **펀드 yaml 유지** | 펀드에만 존재. `.ttl` 하위 클래스로는 가되 **횡단 매핑이 필요 없음** |
| `class_hierarchy`(법적 5분류) · `axis_mapping` | ⬜ **펀드 yaml 유지** | 펀드 고유 분류축 |
| `cross_domain.상장지수_중복`(23종) | 🔼 **`shared/`** | 🔴 펀드↔ETF `owl:sameAs` — 정의상 횡단 |

**채권·ETF 담당자도 자기 파일에 도메인 전용 개체 블록을 추가해야 합니다** (§5 일정 참조).

### 2.5 `.ttl` 과 KG 는 생성합니다 — 손으로 쓰지 않습니다

```
ontology/enums/*.yaml  ┐
ontology/shared/*.yaml ├──▶  scripts/build_ontology.py  ──┬──▶ ontology/*.ttl  (5개, 제출물)
ontology/codebooks/*.csv ┘                                └──▶ data/…db  kg_* 테이블 (런타임)
```

| | 손으로 `.ttl` 작성 | **yaml → 생성 (채택)** |
| :--- | :--- | :--- |
| 워크샵에서 판정이 바뀌면 | `.ttl` · yaml 양쪽 수정 | yaml 만 고치고 재생성 |
| 진실의 원천 | 둘 — 어긋나면 판별 불가 | 하나 |
| 소스코드 20점 | 산출물만 보임 | **파이프라인이 보임** |

> `.ttl` 은 **제출물 겸 스키마 단일 원천**, KG 는 **런타임 조회용**입니다. 둘 다 yaml 에서 나옵니다.
> 사람이 `.ttl` 을 직접 고치는 순간 이 구조가 깨집니다 — **`.ttl` 은 생성물이라고 못 박습니다.**

---

## 3. 무엇을 온톨로지에, 무엇을 KG에 담나

### 3.1 판별 기준 — 두 줄이면 끝납니다

> **① "데이터가 완벽했어도 참인가?"**
> 참 → `.ttl`(구조) 또는 KG(관계) · 거짓 → `yaml`
>
> **② "이 값으로 다른 테이블을 찾아가야 하는가?"**
> 예 → KG 개체 · 아니오 → SQLite 컬럼 그대로 (**범주형이어도**)

| 사실 | 완벽해도 참? | 위치 |
| :--- | :-: | :--- |
| ETF 와 ETN 은 다른 상품이다 | ✅ | `.ttl` |
| 위험등급은 낮을수록 위험하다 | ✅ | `.ttl` |
| 삼성자산운용이 KODEX 200 을 운용한다 | ✅ | KG |
| `cu_charge_rt` 의 `0` 은 미입력이다 | ❌ | `yaml` |
| 국내ETF 총보수 유효 모수는 67건이다 | ❌ | `yaml` |

🔴 **"범주형이면 KG"가 아닙니다.** 펀드 `or_attr_desc`(11종)는 범주형이지만 펀드에만 있으니 KG 에 안 갑니다. 반대로 위험등급은 4테이블에 걸치고 표기가 3종이라 KG 에 갑니다.

### 3.2 yaml 블록 → 어디로 가는가

| yaml 블록 | `.ttl` | KG | 런타임 코드 |
| :--- | :-: | :-: | :-: |
| `columns.*`(결측 판정 · 센티넬 · `answerable_n` · `answer_policy`) | ❌ | ❌ | ✅ |
| `columns.*.layer`(단위·방향·개념) | ✅ 속성 정의 | — | ✅ 교차 정렬 차단 |
| `columns.*.kg_entity` | — | ✅ **포인터** | — |
| `normalization` | ❌ | ✅ | ✅ |
| `query_rules` | ❌ | ❌ | ✅ SQL 주입 + 사후 검사 |
| `shared/*.nodes[].aliases` | — | ✅ **KG 본체** | — |
| `shared/*.absent_in` | ✅ **속성 부재** | ❌ | ✅ 즉시 기각 |
| `entities`(도메인 전용) | ✅ 클래스·관계 | ✅ 노드 | — |
| `class_hierarchy` | ✅ | ❌ | — |
| `axis_mapping` / `axis_derivation` | ✅ `skos:Concept` | ❌ | ✅ 유도 규칙 |
| `attributes` | ✅ DatatypeProperty | ❌ | — |
| `cross_domain` | ✅ `sameAs` 선언 | ✅ 매핑 행 | — |

한 줄 요약: **`entities`·`class_hierarchy`·`attributes` → 온톨로지 / `aliases`·`cross_domain` → KG / 나머지 → 코드.**

### 3.3 🔴 KG 에 들어가는 건 "값"이지 "행"이 아닙니다

가장 헷갈리는 지점이라 따로 씁니다.

```
❌ 오해 1 : KG 에 컬럼명만 넣는다
             → 컬럼명만 있으면 WHERE 에 넣을 값이 없습니다

❌ 오해 2 : 상품 145,393건을 전부 노드로 만든다
             → SQLite 가 이미 갖고 있는 걸 복제하는 것뿐이고, 원본이 갱신되면 어긋납니다

✅ 정답    : 그 컬럼의 서로 다른 값(distinct) 만 넣는다. 컬럼명 + 값이 한 쌍입니다
```

**"이 상품이 삼성 것"이라는 사실은 KG 에 없습니다** — `cu_fund_mgmt_co` 컬럼이 행마다 이미 갖고 있으니까요. KG 는 *"'삼성자산운용'으로 물어봤을 때 그 컬럼에서 무엇을 찾아야 하는가"* 만 답합니다.

```
질의 "삼성자산운용이 운용하는 미국 ETF"
  KG   → cu_fund_mgmt_co = '삼성'                ← 값 하나 얻고 끝. 수치 없음
  SQL  → WHERE cu_fund_mgmt_co='삼성' AND …       ← 행을 찾는 건 SQLite
```

> **KG 에 행이 생기는 조건 = SQLite 의 어느 컬럼으로도 표현되지 않는 연결일 때만**
> · 표기가 갈려서 **못 찾아가는** 것 → `alias` 행 (**값 단위**)
> · **컬럼 자체가 없는** 관계 → `edge` 행 (**행 단위**, 대부분 외부 수집)
> · 나머지 전부 → SQLite 가 이미 담고 있으므로 **넣지 않음**

| | 행 수 |
| :--- | ---: |
| ✅ alias 방식 (distinct 값만) | **약 1만** |
| ❌ 상품마다 엣지 (145,393 × 6종) | 약 87만 |

**📊 차원 / 사실 — 스타 스키마와 같은 구분입니다**

```
KG = 차원 (무엇으로 찾아가나)        SQLite = 사실 (답이 되는 값)
     운용사 · 지수 · 지역                    수익률 · AUM · 보수 · 종가
     자산군 · 위험등급 · 통화                + KG 에 안 간 범주형 전부
```

---

## 4. KG 테이블 — 실제 스키마

트리플스토어 안 씁니다. **SQLite 테이블**입니다 (재현성·의존성 근거, 스펙 §1.3).

```sql
CREATE TABLE kg_node (
  node_id TEXT PRIMARY KEY,   -- 'Org_MiraeAsset'
  node_type TEXT,             -- Organization|Index|Region|AssetClass|RiskGrade|Currency
  canonical_name TEXT,        -- '미래에셋자산운용'
  label_ko TEXT, label_en TEXT
);

CREATE TABLE kg_alias (       -- ★ 노동량의 대부분이 여기
  node_id TEXT, table_name TEXT, column_name TEXT, raw_value TEXT,
  source TEXT                 -- 'codebook_v1' / 'manual' / 'rule'
);

CREATE TABLE kg_edge (        -- SQLite 에 컬럼이 없는 관계만
  src_id TEXT, predicate TEXT, dst_id TEXT,
  source TEXT, as_of TEXT     -- 🔴 외부 데이터는 as_of <= '2026-07-11' 하드 필터
);

CREATE TABLE kg_closure (ancestor_id TEXT, descendant_id TEXT);
                              -- 일본 ⊂ 아시아 ⊂ 글로벌 — 빌드 타임 전개, 런타임 비용 0
```

**`kg_alias` 예시**

| node_id | table_name | column_name | raw_value |
| :--- | :--- | :--- | :--- |
| Org_MiraeAsset | `domestic_etfs` | `cu_fund_mgmt_co` | `미래에셋` |
| Org_MiraeAsset | `public_funds` | `or_co_xtn_itt_cd` | `00080012` |
| Org_MiraeAsset | `overseas_etfs` | `cu_fund_mgmt_co` | `Mirae Asset Global Investments` |
| Curr_KRW | `domestic_etfs` | `pd_curr_cd` | `CURR_CD_KRW` |
| Curr_KRW | `domestic_bonds` | `CURR_CD` | `KRW` |

**`kg_edge` 에 들어갈 것 — 3종뿐입니다**

| 관계 | 왜 KG 인가 | 규모 | 상태 |
| :--- | :--- | ---: | :--- |
| ETF ↔ 편입종목(Holdings) | 4테이블 전부 **컬럼 없음** | 국내ETF 1,202종 × N | 트랙2b |
| 기업 ↔ 자회사 | 컬럼 없음 (에코프로 3-hop) | — | 안건 A-1 |
| 펀드 ↔ ETF `sameAs` | ID 로 안 이어짐 (종목명 일치로만) | **23행** | 오늘 결정 |

### 4.1 alias 규모 — 손으로 만들 건 약 1,200행입니다

| 개체 | alias ≈ | 방식 |
| :--- | ---: | :--- |
| Organization | 8,570 | 🔴 채권 발행사 8,018 은 **규칙 정규화**(`(주)` 위치·공백) + 상위 N 만 검수.<br>손으로 만들 건 **운용사 67 + 수탁사 18 + 국내ETF 32 + 해외 372** |
| Index | 2,140 | 해외 1,733 은 센티넬 2종 제거 후 자동. **핵심은 국내 통용 17종** |
| Region | 98 | 전수 수작업 + 계층 closure |
| AssetClass | 86 | 전수 수작업 (🔴 `Alternatives` 1,760건은 국내 대응 없음 — 명시적으로 "대응 없음") |
| RiskGrade | 25 | 규칙 (`뒤 2자리 − 10`) |
| Currency | 9 | 수작업 |

> ⚠️ **값이 이미 같으면 alias 행이 필요 없습니다.** `pd_grp_no` 의 `'ETF'`/`'ETN'` 은 국내·해외 표기가 동일해서 `.ttl` 엔 제약으로 들어가지만 KG 엔 안 들어갑니다.

---

## 5. 일정 — 5일 (8/17 → 8/21)

**순서를 뒤집으면 재작업이 납니다.**

| # | 단계 | 기간 | 담당 | 완료 판정 |
| :-: | :--- | :--- | :--- | :--- |
| ① | **워크샵** — §8 안건 결정 + `shared/` 규격 확정 | 반나절 | 전원 | 안건표 전부 결론 |
| ② | 🔴 **`shared/*.yaml` 6종 작성** | 2일 | 분담 ↓ | alias 행이 채워짐 |
| ②' | 각자 yaml 에 `kg_entity` · `layer` 소급 기입 | ②와 동시 | 각 담당 | 6개 개체에 걸리는 컬럼 전부 |
| ③ | `build_ontology.py` + `.ttl` 5종 생성 | 1일 | Song-exp | `ontology/*.ttl` 5개 |
| ④ | yaml `canonical_*` 결선 (런타임이 KG 를 실제로 조회) | 1일 | Song-exp | 질의 → KG → SQL 이 돎 |
| ⑤ | 🔴 **검증 게이트** | 반일 | 전원 | ↓ |

**②의 분담** (스펙 §7.7 배치 유지 — 자기가 EDA 한 테이블의 값을 가장 잘 압니다)

| 담당 | `shared/` 파일 |
| :--- | :--- |
| **Song-exp** | `organization.yaml` (운용사·수탁사 코드) · `currency.yaml` |
| **seohynun** | `risk_grade.yaml` · `asset_class.yaml` |
| **LEEbyeoungchul** | `index.yaml` · `region.yaml` (+ 계층 closure) |

**⑤ 검증 게이트 — 여기서 통과 못 하면 `.ttl` 은 장식입니다**

각자 만든 질의 중 **네거티브·미제공 문항**만 골라 아래가 실제로 일어나는지 확인합니다.

```
"신용등급 AAAA 채권"       → CRD_GRD enum 20종에 없음      → 기각  (HCX 0회)
"위험등급 낮은 해외ETF"    → absent_in.overseas_etfs        → unanswerable
"보수 낮은 펀드"           → attributes 에 보수 없음         → "데이터 미제공"
"보수 낮은 ETF"            → 답하되 answerable_n=67 명시
"채권형 ETF Top3"          → pd_grp_no='ETF' 자동 주입       → ETN 안 섞임
```

> 기각 사유가 `think_trace` 에 문장으로 찍혀야 합니다 — *"온톨로지상 `OverseasETF` 클래스에 `riskGrade` 속성이 정의되어 있지 않음"*. **이게 근거 제시 배점입니다.**

---

## 6. 🔴 지금 막혀 있는 것 — 두 개

| 차단 요인 | 무엇이 안 되나 | 조치 |
| :--- | :--- | :--- |
| **운용사 67 + 수탁사 18 이름 없음** | KG 노드에 **레이블이 없어** *"미래에셋자산운용이 운용하는 펀드"* → 11,139종목 전체 조회 불가. **이름 없는 노드는 그래프에 있어도 질의와 안 이어집니다** | 85행짜리 CSV 하나. `docs/DATA_NEEDS.md` ①.<br>🔴 **8자리 전체를 키로** (뒤 4자리만 쓰면 12건이 뭉침) |
| **채권 yaml 없음** | 생성기 입력이 비어 채권이 `.ttl`·KG 에 **통째로 안 들어감**. 함정이 가장 많은 테이블(40컬럼)에 런타임 규칙 0 | 트랙3-3a. ②보다 먼저 |

둘 다 **②의 선행 조건**입니다. 오늘 회의에서 착수 시점을 못 박습니다.

---

## 7. 하면 안 되는 것

| 금지 | 왜 |
| :--- | :--- |
| **KG 에 수치 넣기** (수익률·AUM·보수) | 차원/사실 구분이 무너짐. KG 는 `WHERE` 만 만듭니다 |
| **파생 컬럼 만들기** | 판정이 워크샵에서 바뀝니다. 규칙은 yaml 에 선언 (최악 236ms = 예산의 1.6% — 성능은 이유가 못 됨) |
| **`.ttl` 을 손으로 고치기** | 생성물입니다. 고치면 진실의 원천이 둘이 됩니다 |
| **`.ttl` 에 질문 유형(`qtype`) 넣기** | 도메인 모델이 아니라 앱 로직 |
| **답변불가를 유사도 임계값으로 판정** | 벡터는 항상 top-k 를 반환 → **"없음"을 만들지 못합니다** |
| **결측 채우기 · 센티넬 삭제** | 지우는 순간 *"왜 없는지"* 를 답할 근거가 사라집니다 |

---

## 8. 오늘 결정할 것 — 체크리스트

**구조 (이 문서에서 새로 올리는 안건)**

- [ ] `ontology/shared/<entity>.yaml` 2층 구조 채택 여부
- [ ] `.ttl` 을 **생성물**로 확정 (사람이 직접 편집 금지)
- [ ] `shared/` 6종 담당 배분 (§5 표대로 갈지)
- [ ] `kg_entity`·`layer` 소급 기입 마감 시점

**스펙 §7.4① 기존 안건 — 결정해야 ②를 시작할 수 있는 것**

- [ ] 상장지수 **23종 중복** — `owl:sameAs` 병합 vs 펀드 쪽 제외 (*"ETF 몇 개야"* 이중 계상)
- [ ] **AUM 통화** — 국내 원 / 해외 USD. 환산할지, 교차 정렬을 금지할지 (🔴 환율 데이터 없음)
- [ ] **"수익률" 속성 분리** — `realizedReturn`(ETF·펀드) vs `yieldToMaturity`(채권). **공통 상위 속성 금지**
- [ ] 채권 **위험등급 `0` 58건** — `Unclassified` 별도 개체로 둘지
- [ ] `Alternatives` 1,760건 — "국내 대응 없음" 선언 방식
- [ ] **A-1** 지배구조·테마 엣지를 그래프에 넣을지 (예시 질의 3·4·5가 전부 여기 걸림)
- [ ] **A-2** 생성 SQL 사후 문자열 검사 (`TRIM`·`pd_grp_no`·`GROUP BY` 가 실제로 들어갔는지)
- [ ] **A-7** 오류 응답 200 vs 500 (재시도 2회를 살릴지)
- [ ] **구성종목** — "어디까지" (해외ETF 포함? 종목당 상위 N?)

**⚠️ 주최 자료와 실측이 다른 것 — 제안서에 근거 병기**

주최 예시는 `riskGrade 1~5` 인데 실측은 **0~6** 이고 6등급이 채권 24.6%(10,408건)입니다.
→ `.ttl` 과 제안서에 **한 줄 병기**: *"주최 예시는 1~5이나 제공 데이터 실측 결과 0~6이며, 1~5로 제약 시 채권 24.6%가 차단되어 0~6으로 정의함"*

---

## 부록: 참고 문서

| 문서 | 내용 |
| :--- | :--- |
| `.agents/rules/miraeasset-rules.md` | **확정 규칙** (이 문서보다 우선) |
| `docs/superpowers/specs/2026-08-12-ontology-design-and-roadmap.md` | 설계 근거 전체 · 워크샵 안건 원문 (§7.4①) |
| `docs/NEXT_STEPS.md` | 앞 단계 지시서 · **yaml 컬럼 층 규격** (§5.1) |
| `docs/EDA_GUIDE.md` | EDA 방법 · 확인된 데이터 함정 |
| `docs/DATA_NEEDS.md` | 외부 수집 필요 목록 (① 운용사·수탁사 이름 최우선) |
| `docs/eda/*_notes.md` (4종) · `docs/domain/*.md` (2종) | 판정 근거 |
| `PROJECT.md` | 과제 개요 · 배점 · API 명세 |
