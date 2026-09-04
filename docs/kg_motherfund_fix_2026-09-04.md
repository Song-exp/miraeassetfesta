# 지시서 — KG 접지 불가 노드 정리 (모펀드 · 이름폴백) · 2026-09-04

> 대상: `kg_node` 의 `MotherFund_*` 717 · `Sec_on_*` 중 alias 미부착 84
> 생성기: `scripts/gen_fund_structure_auto.py` · `scripts/gen_security_auto.py`
> 반영 경로: yaml 수정 → `python scripts/build_ontology.py` 재실행 → ttl·`kg_*` 재생성

---

## 0. 왜 하는가

`Fund` 노드 7,584개가 **성질이 다른 두 모집단**을 한 타입에 담고 있다.

| | 수 | alias | closure | edge | 마스터 매칭 |
| :-- | --: | --: | --: | --: | --: |
| rptt 예탁원번호 묶음 | 6,867 | 있음 | 0 | 0 | 해당 |
| `MotherFund_*` | **717** | **0** | **0** | feedsInto | **0 / 717** |

제출물과 시각화에 "Fund 7,584" 로 나가는데, 그 숫자는 **한 뜻이 아니다.**

---

## 1. 사실 확인 (재현 가능)

```sql
-- ① MotherFund 는 마스터 어느 행과도 이름이 일치하지 않는다
SELECT COUNT(*) FROM kg_node n WHERE n.node_id LIKE 'MotherFund_%'
  AND EXISTS (SELECT 1 FROM public_funds p
              WHERE REPLACE(p.itm_nm,' ','') = REPLACE(n.canonical_name,' ',''));
-- → 0 / 717
```

생성기도 같은 말을 기록해 두었다:

> `gen_fund_structure_auto.py:20` — *"마스터 itm_nm 과 정규화 완전일치는 3건뿐 → 모펀드는 마스터 밖 개체(`MotherFund_*`)로 생성하고 feedsInto 로 잇는다"*

**② 원천이 설명서 산문 덩어리다.** `ext_fund_page.mother_fund_names_raw` 실제 값:

```
각모투자신탁;이투자신탁은채권및주식에각각주로투자하는모투자신탁;집합투자재산의대부분을채권모투자신탁과주식모투자신탁
```

세미콜론으로 쪼개 노드를 만든 결과:

| 증상 | 수 | 예 |
| :-- | --: | :-- |
| 문장 조각이 노드가 됨 | **92 (13%)** | `하는모투자신탁` · `투자하고모투자신탁` · `증권모투자신탁` · `-모투자신탁` |
| `증권` 유무만 다른 중복 쌍 | 8쌍 | `삼성통일코리아모투자신탁` / `삼성통일코리아증권모투자신탁` |
| 10자 이하 조각 | 61 | |

**③ 답변에 기여하지 않는다.** 2026-09-04 실측 `KG-010`("미래에셋코어테크 펀드의 모펀드는 뭐야?")은 ✅ 통과했으나 **`ext_fund_page.mother_fund_names_raw` 로 답했다.** KG 717 노드는 경로에 없었다.

**④ 마스터에 모펀드 행은 없다.** `itm_nm LIKE '%모투자신탁%'` 1,970행은 전부 **'사<u>모투자신탁</u>'** 부분일치다(공모/사모의 사모). 진짜 모펀드가 아니다.

⚠️ 다만 **개념 자체는 있다** — 종목명 `자투자신탁` 7,693행(모자형 자펀드 표식) · `mother_fund_names_raw` 4,185행 · 도메인 PDF §3.2. 없애는 게 아니라 **제자리를 찾아주는 일**이다.

---

## 2. 할 일

### 2-1. 🔴 노드 타입을 분리한다

`kg_node.node_type` 을 `Fund` → **`MotherFund`** 로 (id 접두가 이미 `MotherFund_` 라 판정이 자명하다).

- `scripts/gen_fund_structure_auto.py` 의 `mother_nodes` 생성부에서 타입을 지정
- `ontology/shared/fund_structure_auto.yaml` 재생성
- `common.ttl` 에 `fp:MotherFund a owl:Class .` 추가 — **`fp:Product` 하위로 두지 않는다**(판매 상품이 아니다)
- `feedsInto` 의 range 를 `fp:MotherFund` 로
- 🔴 **`common.ttl` 을 직접 고치지 않는다** — 생성물이다(`DO NOT EDIT`). 클래스 선언은 `build_ontology.py` 의 `emit_ttl` 이 내보내게 한다

🔴 **런타임 동반 수정 (빠뜨리면 조용히 동작이 바뀐다)**

```python
# src/runtime/pipeline.py:6014  _ground()
if name_mode and node.node_type in ("Organization", "Fund"):        # ← 현재
if name_mode and node.node_type in ("Organization", "Fund", "MotherFund"):   # ← 이렇게
```

`_ground()` 는 라벨로 노드를 맞춘다. 타입만 바꾸고 이 줄을 안 고치면 모펀드 이름으로 물었을 때
'이름 모드' 분기를 타지 못한다. **타입 분리와 같은 커밋에 넣는다.**

기대 결과: `Fund` **6,867** · `MotherFund` **717** 로 갈린다.

### 2-2. 🔴 조각·중복 — **지우지 말고 표시한다** (2026-09-04 재측정으로 방침 변경)

처음엔 "조각을 버린다" 로 적었으나, 실제로 재어 보니 **버리면 그래프가 크게 상한다.**

| 실측 | 값 |
| :-- | --: |
| 조각 판정 노드 (접미 잔여 2자 미만 · 조사/어미 시작) | **109** |
| 이들이 받는 `feedsInto` | **418 / 1,704 (25%)** |
| **조각에만 연결된 자펀드** (지우면 관계를 완전히 잃는다) | **177 / 965** |

`증권모투자신탁` 같은 조각은 **여러 자펀드가 공유**하는 절단 이름이라, 노드 하나를 지우면
간선이 무더기로 사라진다. 그리고 원문이 이미 잘린 상태라 **복원할 정본이 없다.**

→ **방침: 노드를 유지하되 품질을 표시한다.**

| 조치 | 내용 |
| :-- | :-- |
| `status: parse_fragment` 부여 | 109개. 간선은 그대로 살린다 |
| 커버리지 리포트·시각화 개수에서 **분리 집계** | "MotherFund 717 (그중 파싱 조각 109)" |
| `증권` 유무 중복 8쌍만 **병합** | 이건 복원 가능한 중복이라 안전하다 |
| 답변 경로에서 조각 이름을 **인용 금지** | 사용자에게 `하는모투자신탁` 을 보여주면 안 된다 |

기대 결과: 노드 수는 **717 → 709**(중복 8쌍 병합분만 감소), `feedsInto` 는 **1,704 유지**.

⚠️ 조각을 정말 없애려면 **파서를 고쳐 원문에서 다시 뽑아야** 한다(세미콜론 분리 대신 문장 경계·
접두 브랜드 인식). 그건 이 지시서 범위 밖이고, 프리즈 후 과제다.

### 2-3. 🟡 `Sec_on_*` 이름폴백 정리

`Security` 27,996 중 `Sec_on_*` 이 744개(해외 보유종목 이름 매칭 폴백, `gen_security_auto.py:151` `status="name_fallback"`).

| | 수 | 처리 |
| :-- | --: | :-- |
| alias 부착됨 | 660 | 유지 |
| **alias 0 · closure 0 · edge 0** | **84** | 접지 불가 — 제거하거나 `status` 를 명시해 리포트에서 분리 |
| `canonical_name` NULL | **744 전부** | `label_en` 을 `canonical_name` 으로 채운다 (라벨 정본 부재) |

모펀드와 달리 **이름은 정상**이다(`ACCTON TECHNOLOGY CORPORATION` 등). 우선순위는 낮다.

### 2-4. 재생성·검증

```bash
python scripts/gen_fund_structure_auto.py
python scripts/gen_security_auto.py
python scripts/build_ontology.py --check      # 오류 0 · 경고는 기존 8건 유지 확인
python scripts/build_ontology.py
```

⚠️ `build/viz_kg.json`·`kg.html` 은 **08-26 짜리로 9일 낡았다**(노드 39,677 vs 현재 41,580). 이번에 함께 재생성한다.

---

## 3. 검증 조건

| # | 확인 | 통과 |
| :-: | :-- | :-- |
| 1 | `SELECT node_type, COUNT(*) FROM kg_node GROUP BY 1` | `Fund` 6,867 · `MotherFund` **709** |
| 2 | 조각 표시 | `status='parse_fragment'` **109개** — 지우는 게 아니라 표시다 |
| 3 | `증권` 유무 중복 | **0쌍** |
| 4 | `feedsInto` 간선 수 | **1,704 그대로** (조각을 지우지 않으므로 줄지 않는다) |
| 5 | `build_ontology.py --check` | 오류 0 · 경고 8(기존 pending) |
| 6 | 서버 실측 `KG-010` | 여전히 ✅ — 이 경로는 `ext_fund_page` 라 KG 변경에 영향받지 않아야 정상 |
| 7 | 서버 실측 회귀 4문항 | `KG-025` 207/240 · `X9` 823/230 · `S8` 129 · `R1` 19범주 |
| 8 | `pipeline.py:6014` | `"MotherFund"` 가 목록에 있는가 |

---

## 4. 하지 말 것

- 🔴 **`MotherFund` 노드를 통째로 삭제하지 말 것.** `feedsInto` 1,704가 `Fund` 타입이 참여하는 유일한 간선이라, 지우면 KG 고립 노드 비율이 88% → 더 나빠진다. 분리와 정리이지 제거가 아니다.
- 🔴 **`fp:Fund` 를 `fp:Product` 하위로 만들지 말 것.** 지금 `fp:Fund a owl:Class .` 만 있고 상위가 없다 — 이게 맞다. 펀드 묶음은 판매 단위가 아니다.
- 🔴 **마스터에 모펀드 행을 만들지 말 것.** 주최 데이터에 없는 행을 만드는 것은 규정 밖이다.
- 🟡 `entities` 블록의 서술을 지우지 말 것 — `belongsToFund` 가 0인 **이유**가 거기 적혀 있다(§5 참조).

---

## 5. 곁가지 — 이 작업이 드러낸 구조 문제

`entities` 블록에 이런 문장이 있다:

> 🔴 KG 에 FundClass 노드는 없고 `belongsToFund` edge 도 0건이다. **이것은 결함이 아니라 설계다** — 클래스→묶음 관계를 `rptt_ksd_itm_no` 가 이미 담고 있어 23,676 노드를 중복 생성하지 않는다

맞는 판단인데 **이 근거가 ttl 에 안 나간다.** `build_ontology.py` 는 enums yaml 에서 `columns`·`absent_properties`·`domain` 만 읽는다. 그래서 ttl 에는 `fp:belongsToFund` 선언만 남고 "왜 비었는가" 는 사라진다 — 밖에서 보면 못 채운 약속으로 읽힌다.

같은 모양이 **14개 속성**에 있다(`manages`·`holds`·`hasManager`·`hasRiskGrade` …). 인스턴스 트리플이 있는 것은 `hasAssetClass`(3,172)와 `successor`(1) 둘뿐이다.

→ **후속 과제**: `absent_properties` 가 속성에 하는 일(선언 + 이유 + 대체 안내)을 **관계에도** 한다. 이미 검증된 메커니즘이다(2026-09-04 실측에서 ABSENT 4종 4/4 통과). 이번 작업 범위 밖이지만 같은 뿌리다.

---

## 6. 일반 전략 — 접지 불가 노드를 판정하는 규칙

이번 건은 개별 수정이지만, **같은 판정을 매번 손으로 하지 않도록** 규칙으로 굳힌다.

### 6-1. 노드의 자격은 세 신호로 갈린다

| 신호 | 뜻 |
| :-- | :-- |
| `kg_alias` | 질의의 표기를 DB 값으로 옮길 수 있다 — **접지** |
| `kg_closure` | 아래에 실물 노드가 매달려 있다 — **정본·허브** |
| `kg_edge` | 다른 개체와 관계가 있다 — **관계 참여** |

셋 중 **하나도 없으면 그 노드는 어떤 질의에도 쓰이지 않는다.**

### 6-2. 4분류와 처방

| # | alias | closure | edge | 부류 | 처방 |
| :-: | :-: | :-: | :-: | :-- | :-- |
| ① | 있음 | — | — | **접지 노드** | 유지. KG 의 본체 |
| ② | 0 | >0 | — | **정본 노드** | 유지. alias 0 이 정상이다 — 존재 이유가 closure 다 |
| ③ | 0 | 0 | >0 | **관계 전용 노드** | 🔴 **별도 타입으로 분리** + 이름 품질 검사. 접지 노드와 같은 타입에 두면 개수가 두 뜻을 섞는다 |
| ④ | 0 | 0 | 0 | **완전 고아** | 🔴 제거하거나 `status: pending` 으로 **사유를 명시**. 사유 없는 ④ 는 빌드 경고 |
| ⑤ | 0 | 0 | 0 | **모호 표시 노드** | ✅ **유지** — alias 를 뺀 것이 판정 결과다. `ambiguous_names` 같은 사유 필드가 있으면 ④ 가 아니다(2026-09-04 `Sec_on_*` 84건: 이름이 다른 종목과 겹쳐 alias 제외 — 삼성전자↔삼성전기 오병합 방지) |

### 6-3. 현재 전수 (2026-09-04 실측)

| 부류 | 대상 | 조치 |
| :-- | :-- | :-- |
| ② 정본 | `Index` 58 · `Security` 14(`Sec_m_*`) · `CreditGrade` 2 | ✅ 그대로 — 설계다 |
| ③ 관계 전용 | **`Fund`/`MotherFund` 717** | 🔴 §2-1·2-2 (이 지시서) |
| ④ 고아 · 사유 있음 | `CreditGrade` 5 · `Currency` 1 | ✅ 그대로 — 1차엔 있고 2차엔 없음, `pending` 기록됨 |
| ⑤ 모호 표시 | `Security`/`Sec_on_*` **84** | ✅ 유지 — `ambiguous_names` 기록 보유(2026-09-04 정정) |

**부류 ③·④ 는 지금 이 둘이 전부다.** 나머지 8개 타입(`Organization`·`Region`·`FundAttribute`·`Country`·`AssetClass`·`RiskGrade` …)은 alias 0 노드가 하나도 없다.

### 6-4. 상시 검사 쿼리

수정 후·재생성 후 이걸 돌린다. 새 부류 ③·④ 가 생기면 바로 보인다.

```sql
SELECT n.node_type,
       CASE WHEN a.node_id IS NOT NULL THEN '① 접지'
            WHEN c.n > 0               THEN '② 정본'
            WHEN e.n > 0               THEN '③ 관계전용'
            ELSE                            '④ 고아' END AS 부류,
       COUNT(*)
FROM kg_node n
LEFT JOIN (SELECT DISTINCT node_id FROM kg_alias) a ON a.node_id = n.node_id
LEFT JOIN (SELECT ancestor_id id, COUNT(*) n FROM kg_closure GROUP BY 1) c ON c.id = n.node_id
LEFT JOIN (SELECT id, SUM(n) n FROM (
             SELECT src_id id, COUNT(*) n FROM kg_edge GROUP BY 1
             UNION ALL SELECT dst_id, COUNT(*) FROM kg_edge GROUP BY 1) GROUP BY 1) e ON e.id = n.node_id
GROUP BY 1, 2 ORDER BY 1, 2;
```

### 6-5. 🔴 재발 방지 — `build_ontology.py` 에 `[V8]` 추가

지금 검증은 **alias 가 가리키는 값이 실재하는가**(`V1`)는 보지만, **노드가 아무 데도 안 닿는가**는 안 본다. 그래서 717·84 가 조용히 쌓였다.

> `build_ontology.py` 는 `V1`~`V7` 만 쓴다. `loader.py` 의 "V8 성격" 은 **주석뿐이고 규칙 ID 가 아니다** — 확인함. 그래서 **`V8`** 을 쓴다.

```
[V8] 부류 ④(alias 0 · closure 0 · edge 0) 노드는 경고.
     shared yaml 에 status: pending + 사유가 있으면 [V8p] 로 강등(현행 V1/V1p 와 같은 방식).
[V8r] 부류 ③(관계 전용) 이 접지 노드와 같은 node_type 에 섞이면 경고.
      판정: 같은 node_type 안에서 alias 보유율이 0% 인 id 접두 집단이 있으면 분리 대상.
```

**경고이지 오류가 아니다.** 부류 ②·pending 이 정당하게 존재하므로 빌드를 막으면 안 된다. 다만 리포트(`data/kg_coverage_report.md`)에 절을 하나 만들어 매번 수를 찍어 둔다.

### 6-6. 이름 품질 — 텍스트에서 뽑은 노드에 공통 적용

`MotherFund_*` 의 13% 조각은 **파서가 만든 것**이지 데이터가 아니다. 텍스트 추출로 노드를 만드는 모든 경로(지금은 `gen_fund_structure_auto.py`, 앞으로 설명서·공시 수집이 늘면 더)에 같은 관문을 둔다.

| 검사 | 버리는 조건 |
| :-- | :-- |
| **접미 잔여** | 유형 접미어(`증권`·`모투자신탁`·`투자신탁`·`Corp`·`Inc` …)를 뺀 나머지가 2자 미만 |
| **조사·어미 시작** | `하는`·`투자하고`·`각`·`및`·`-` 로 시작 |
| **부분문자열 중복** | 한 이름이 다른 이름의 부분집합이면 긴 쪽으로 병합 |
| **라벨 정본 부재** | `canonical_name` 이 비면 `label_ko` → `label_en` 순으로 채운다 (`Sec_on_*` 744건이 여기) |

🔴 마지막 줄은 `Sec_on_*` 744개 **전부**에 해당한다 — alias 가 붙은 660개도 `canonical_name` 이 NULL 이라 답변에 이름을 옮길 근거가 약하다. 부류 ④ 84개보다 **이쪽이 영향 범위가 넓다.**

### 6-7. 적용 순서

| 순위 | 할 일 | 범위 |
| :-: | :-- | :-- |
| 1 | `Sec_on_*` 744 `canonical_name` 채우기 | 6-6 마지막 줄 — 가장 넓고 위험 0 |
| 2 | `MotherFund` 타입 분리 + 조각 정리 | §2-1·2-2 |
| 3 | `[V8]`·`[V8r]` 경고 추가 + 커버리지 리포트 절 | 6-5 — 재발 방지 |
| 4 | ~~`Sec_on_*` 고아 84 제거~~ — **철회**(부류 ⑤) | 2026-09-04 |
| 5 | 텍스트 추출 관문을 생성기 공통 함수로 | 6-6 — 다음 수집분부터 적용 |
