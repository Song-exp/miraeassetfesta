# 가드 → 슬롯 인벤토리 (단계 0 · 2026-09-03)

> 절차: `docs/guard_to_yaml_migration_2026-09-03.md` §1. **코드 0줄 — 표만 만든다.**
> 대상: `src/runtime/pipeline.py` 의 `ensure_*` 57개 중 절차 §4 가 지목한 **부류 A 후보 20개**.
> 근거: 각 가드의 docstring(발동 조건·문항 ID가 그대로 적혀 있다) + 본문 실독.
> 판정 기준은 절차 §1 이 정한 그대로 — **발동 조건을 `tables / question / grounded / sql.has / sql.lacks` 다섯 축으로,
> 동작을 6개 `action` 으로 쓸 수 있으면 A(슬롯), 못 쓰면 코드에 남긴다.**

---

## 0. 결론 — 20개가 다 A 는 아니다

절차 §4 는 20개를 부류 A 로 전제했다. 다섯 축·6액션에 실제로 대보니 **셋으로 갈린다.**

| 판정 | 수 | 뜻 | 처리 |
| :-: | --: | :-- | :-- |
| **A** | **9** | 다섯 축 + 액션 1개로 그대로 쓴다 | 슬롯 전환 |
| **A△** | **8** | 규칙은 일반적인데 **스키마가 부족**하다 — 액션 2개 조합이거나, 조건이 "절이 정확히 1개" 같은 **모양(shape)** 이다 | §2 의 스키마 확장 3개를 받으면 A |
| **C** | **3** | SQL 을 **통째로 템플릿으로 교체**한다 — `action` 6종 밖 | 코드 잔류 |

**프리즈 전 P0 3개는 전부 A 다** — 확장 없이 바로 전환할 수 있다. 이것이 이 표의 가장 중요한 결과다.

🔴 절차 §4 P0-2 는 `ensure_fund_distinct_count` + `ensure_fund_distribution_fund_count` 를 한 슬롯(`펀드단위.enforce`)에 묶었는데,
**둘은 액션이 다르다**(`replace_expr` vs `add_select`) — 슬롯 하나에 액션 하나라는 §2-1 규칙과 어긋난다. 슬롯 2개로 나눠야 한다(§3).

---

## 1. 인벤토리 20행

열은 절차 §1 표 그대로. `현재 ✅ 영향` 은 단계 2 섀도 로그에서 채운다(지금은 ⬜).

### 1-1. 판정 A — 다섯 축·1액션으로 그대로 (9개)

| 가드 | 기존 yaml 규칙 | when.tables | when.question | when.sql | action | sql (확정식) | 원자성 | 문항 |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| `ensure_fund_base_population` **P0-1** | `public_funds.기본모수` | `[public_funds]` (UNION·타 상품군 JOIN 이면 불개입) | `not_any: [사모, 판매완료, 역외, 전체]` | `lacks: [sale_yn, prvo_pbff_desc]` · `any_of_has: ["ORDER BY", "COUNT(", "SUM(", "AVG("]` | `inject_where` | `sale_yn='판매중' AND prvo_pbff_desc='공모'` | 주입 후 `M:BASEPOP` 표식 | FND-R06 · paired v2 값불일치 37 |
| `ensure_fund_distinct_count` **P0-2a** | `public_funds.펀드단위` | `[public_funds]` (JOIN·GROUP BY 없음) | `any: [몇 개, 개수]` · `not_any: [클래스]` | `has: ["COUNT(*)"]` · `lacks: ['"펀드수"']` | `replace_expr` | `COUNT(DISTINCT {fund_key}) AS "펀드수", COUNT(*) AS "클래스수"` | `from: COUNT(*)` 가 정확히 잡힐 때만 | FND-034 |
| `ensure_etf_index_canon` **P0-3** | `domestic_etfs` 지수 규칙 | `[domestic_etfs]` | — | `has: [cu_base_index]` | `replace_predicate` | `ref_base_index` 순수추종식 (지수명 또는 CR·TR·PR 접미만) | 비교식 단위 치환 | X7 · Z19 · AA22 · CROSS-002 |
| `ensure_etf_base_population` | `domestic_etfs` 모수 규칙 (**신설**) | `[domestic_etfs]` | `not_any: [ETN, 판매종료, 전체]` | `lacks: [pd_grp_no, pd_sale_yn]` · `any_of_has: ["ORDER BY", "COUNT("]` | `inject_where` | `pd_grp_no='ETF' AND pd_sale_yn=1` | 표식 `M:ETFPOP` | 7R U8 · AA22 |
| `ensure_fund_type_axis` | `public_funds.유형별분포` | `[public_funds]` | `any: [주식형, 채권형, MMF, …]` (유형 값) | `lacks: [zrin_btyp_nm, zrin_ptn_nm, zrin_pcd]` | `inject_where` | `zrin_btyp_nm LIKE '%{type}%'` | 이미 유형 절이 있으면 불개입 | 6R Y7 |
| `ensure_fund_safe_grade_direction` | `answer_rules` 위험등급방향 | `[public_funds]` | `any: [안전, 안정]` · `not_any: [1등급, 2등급, …]` | `has: ["zrin_fd_ivst_risk_gcd = 1", "= 2"]` | `replace_predicate` | `zrin_fd_ivst_risk_gcd = 6` | 등호 절 1개일 때만 | FND-C03 (FND-002 회귀보호) |
| `ensure_fund_return_error_exclusion` | `public_funds.수익률기점오류_제외` | `[public_funds]` | — | `has: [fd_mm18_ern_r, fd_yr2_ern_r, fd_yr3_ern_r, fd_yr5_ern_r]` (ORDER BY 첫 키) · `lacks: [KR5119470012, itm_nm LIKE]` | `inject_where` | 검증 3클래스 `NOT IN (…)` | 제외 코드 이미 있으면 불개입 | FND-019 |
| `ensure_etf_brand_token` | `domestic_etfs.상품명조회` | `[domestic_etfs]` (UNION 없음) | `grounded: Brand` (DB 실측 접두 **정확히 1개**) | `has: [pd_abrv_nm LIKE, pd_nm LIKE]` · `lacks: ["{brand}"]` | `inject_where` | `pd_abrv_nm LIKE '%{brand}%'` | 브랜드 2개 이상이면 불개입 | UNANS-001 · OFFICIAL-004 |
| `ensure_fund_name_filter` | `public_funds.종목명검색` | `[public_funds]` | `grounded: residual_name_token` | `lacks: ["itm_nm LIKE"]` | `inject_where` | `itm_nm LIKE '%{token}%'` | 이름 절 이미 있으면 존중 | FND-016 · FND-R05 |

### 1-2. 판정 A△ — 규칙은 일반적, 스키마가 부족 (8개)

| 가드 | 기존 yaml 규칙 | 부족한 것 | 필요한 확장 | 문항 |
| :-- | :-- | :-- | :-- | :-- |
| `ensure_fund_distribution_fund_count` **P0-2b** | `public_funds.유형별분포` | 조건이 "SELECT 가 **정확히** (라벨, `COUNT(*)`) 2항목" — 모양(shape) 조건이라 `has/lacks` 로 못 쓴다 | `sql.select_shape` 축 | R1 재검 (7~9번째 재발) |
| `ensure_fund_mixed_type` | `public_funds` 유형 규칙 | "유형 조건이 **정확히 1개**" — 절의 **개수** 조건 | `sql.predicate_count` | FND-023 |
| `ensure_fund_country_tag` | `public_funds.국가태그` | 액션 2개 — 컬럼 오용 `replace_predicate` + wrap 없는 LIKE 를 정식형으로 **정규화** | `action` 목록에 `normalize_predicate` | FND-026 |
| `ensure_fund_attr_tag` | `public_funds` 속성태그 규칙 | 액션 2개 — 태그식 `inject_where` + 같은 낱말을 다른 컬럼에 쓴 절 `remove_predicate` | 액션 **배열** 허용 | KG-017 · KG-018 |
| `ensure_fund_series_boundary` | `public_funds.종목명검색` | 액션 2개 — 망가진 호 경계 절 `remove_predicate` + `inject_where` | 액션 배열 | FND-032 |
| `ensure_fund_estb_year` | `public_funds.설명서항목` | 액션 2개 — 날짜 절 전부 `remove_predicate` + `estb_dt` 범위 `inject_where` | 액션 배열 | Z22 · KG-035 · X19 |
| `ensure_fund_entity_count_ranking` | `public_funds` 개수 랭킹 규칙 (**신설**) | 액션 2개 — `replace_order` + 집계식 `replace_expr` | 액션 배열 | KG-008 · AA16 |
| `ensure_fund_rank_representative` | `public_funds.대표행` | 방향 의존 — `ORDER BY` 가 DESC 면 `MAX`, ASC 면 `MIN`. 확정식이 SQL 상태에 따라 갈린다 | `sql` 에 `{sort_agg}` 자리표시자 | FND-015 |

**필요한 스키마 확장은 3개다** — ① `action` 을 배열로(5건이 여기 걸린다) ② `sql.select_shape`·`sql.predicate_count` 모양 축 ③ 자리표시자 `{sort_agg}`. ①만 받아도 8개 중 5개가 A 가 된다.

### 1-3. 판정 C — 일반화 안 됨, 코드 잔류 (3개)

| 가드 | 왜 안 되는가 | 문항 |
| :-- | :-- | :-- |
| `ensure_fund_holdings_template` | 원문 WHERE 의 펀드 술어를 뽑아 **JOIN·GROUP BY·ORDER BY 를 새로 쓴다.** 6액션은 전부 "기존 SQL 의 한 부분을 고치는" 동작이라 표현 불가 | KG-028 · KG-034 · X1 · X2 |
| `ensure_fund_manager_ranking` | SELECT·GROUP BY·집계축·LIMIT 을 통째로 확정 템플릿으로 교체. 질문 어휘에 따라 집계축이 갈린다(순자산 → SUM, 그 외 펀드수) | S11 |
| `ensure_fund_estb_lookup` | `MIN/MAX(e.estb_dt)` + 클래스수 병기 + `ORDER BY` 를 한꺼번에 — 역시 전체 교체 | AA5 · Z9 |

세 가드의 공통점: **"SQL 을 고친다" 가 아니라 "SQL 을 다시 쓴다".** 절차 §6 이 금지한 "다섯 축 밖 조건" 이 아니라 **액션 쪽 한계**다.
필요하다면 나중에 `action: replace_query` + 템플릿 문자열로 열 수 있지만, 그건 "yaml 에 SQL 을 통째로 적는" 것이라
선언이 아니라 코드의 이사에 가깝다 — 이번 범위에서는 코드에 둔다.

---

## 2. 슬롯 스키마에 반영할 것 (단계 1 입력)

절차 §2-1 초안에 더해 아래가 필요하다. 셋 다 다섯 축의 **정신**(선언 가능한 조건만)을 지킨다.

```yaml
enforce:
  when:
    tables: [public_funds]
    question: {any: [...], not_any: [...]}
    grounded: Country              # KG 접지 결과 — Country · Brand · residual_name_token
    sql:
      has: [...]                   # 이 문자열이 SQL 에 있으면
      lacks: [...]                 # 없으면
      any_of_has: [...]            # 🆕 하나라도 있으면 (기본모수의 "ORDER BY 또는 집계")
      select_shape: [label, "COUNT(*)"]   # 🆕 SELECT 항목 구성이 정확히 이것
      predicate_count: {columns: [or_attr_desc, zrin_btyp_nm], eq: 1}   # 🆕 해당 컬럼 절이 정확히 N개
  action: [remove_predicate, inject_where]   # 🆕 배열 허용 — 선언 순서대로 1회씩
  from: "COUNT(*)"
  sql: "..."                       # {code}·{key}·{col}·{fund_key}·{sort_agg} 자리표시자
  mark: BASEPOP
```

🔴 **여기에 더해 반드시 같이 고쳐야 하는 것 — `loader.planner_context` (절차 §7 산출물 목록에 빠져 있다)**

절차 §2-1 은 "`enforce` 는 프롬프트에 싣지 않는다 — 적용기만 읽는다" 를 전제한다. **현재 로더는 그렇게 동작하지 않는다.**
`loader.py:129` 는 `triggers` 가 있는 dict 만 특수 처리하고, 나머지 dict 는 `yaml.safe_dump(rule)` 로 **통째로** 덤프한다.
절차 §2-1 예시 모양(`기본모수: {text:, enforce:}`)을 그대로 넣고 재현한 결과:

```
프롬프트에 enforce 가 새는가: True     ← when·action·sql·mark 가 전부 프롬프트에 실린다
```

문자열 규칙을 dict 로 바꾸는 **모든** 슬롯 규칙에서 발생한다. `planner_context` 가 dict 에서 `text` 만 꺼내도록 하는 한 줄이 단계 1 에 포함돼야 한다.

---

## 3. 절차 §4 전환 순서에 대한 수정 제안 1건

**P0-2 를 슬롯 2개로 나눈다.** 절차는 `ensure_fund_distinct_count` + `ensure_fund_distribution_fund_count` 를
`펀드단위.enforce` 하나에 묶었는데, 전자는 `replace_expr`(COUNT(*) → 펀드수+클래스수)이고
후자는 `add_select`(분포 3열에 펀드수 병기)다. §2-1 의 "슬롯 하나에 액션 하나" 와 어긋나고,
후자는 `select_shape` 확장이 있어야 쓸 수 있다(A△).

| 수정 | 슬롯 | 가드 | 프리즈 전 |
| :-- | :-- | :-- | :-: |
| P0-2a | `펀드단위.enforce` | `ensure_fund_distinct_count` | ✅ 확장 불필요 |
| P0-2b | `유형별분포.enforce` | `ensure_fund_distribution_fund_count` | `select_shape` 확장 후 |

→ **프리즈 전 확장 없이 전환 가능한 것은 P0-1 · P0-2a · P0-3 셋.** 절차의 "P0 3개" 와 개수는 같고 내용이 하나 다르다.

---

## 4. 다음 (단계 1)

1. `loader.py` — `planner_context` 의 `text` 추출 + `enforce` 스키마 검증(V8 성격)
2. `guard.py` — `apply_enforce(sql, q, tables, grounded, ctx) -> (sql, fired)`
3. `ontology/enums/public_funds.yaml` · `domestic_etfs.yaml` — A 판정 9개의 `enforce` 블록 (**발동은 단계 2 섀도부터**)

단계 2 섀도의 문항 셋 94개는 **아직 만들 수 없다** — 15R ❌30 의 qid 목록이 리포에 없다
(`eval/verdicts_merged.json` 은 13R 까지, `docs/answer_quality_by_type_2026-09-03.md` 는 30건 중 11건만 ID 지명).
규칙 전달 감사 §4-3 도 같은 이유로 대체 셋을 쓰고 있다. **리드 확인 필요.**
