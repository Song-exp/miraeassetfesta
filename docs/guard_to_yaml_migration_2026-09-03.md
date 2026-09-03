# 작업 절차 — 코드 가드에 흩어진 수리를 일반화해 yaml 로 옮기고, 실제로 적용되게 만들기 (2026-09-03)

> 대상: `src/runtime/pipeline.py` 의 펀드 결합 `ensure_*` 30개 중 **"규칙은 yaml 에 이미 있고 가드는 그 확정식을 코드로 재강제한" 20개**(부류 A). 표시·묶기(부류 B 4개)와 SQL 위생(부류 C 6개)은 코드에 남는다.
> 원칙: **선언이 먼저, 코드는 그 선언을 읽는 제네릭 적용기 하나.** 가드를 먼저 지우지 않는다. 슬롯이 발동한 뒤 가드가 침묵하는 것을 확인하고 나서 뗀다.
> 관계: `docs/rule_delivery_audit_2026-09-03.md`(전달 감사)는 병렬로 돈다. 이 절차는 감사 결과를 기다리지 않는다 — enforce 슬롯은 context form 의 상위 호환이라 어느 결과가 나와도 유효하다. 감사가 "형식만 고치면 산다"고 판정한 규칙은 슬롯을 비활성(`enforce: off`)으로 두면 된다.
> 프리즈 9/6. 프리즈 전에는 §4 의 P0 3개(+여유 시 P1)만 전환하고 나머지는 슬롯 정의만 해 둔다.

---

## 0. 왜 이 순서인가 (한 단락)

가드 30개는 각각 "발동 조건 ①②③ + 확정식 + 동작(주입/교체/제거)"이라는 같은 뼈대를 파이썬으로 다시 쓴 것이다. 뼈대가 같으니 데이터로 표현할 수 있고, 데이터가 되면 ① UNION 가지든 단일 문장이든 같은 조건에 같은 규칙이 붙고(교차질의 16건의 원인 제거) ② 채권·ETF 도 같은 슬롯을 써서 "ETF 쪽엔 모수 가드가 아예 없었다" 류 누락이 구조적으로 사라지며 ③ 가드끼리의 순서 의존(8R~13R 실패 5변종)이 선언 순서 하나로 정리된다. 반대로 코드에 두면 문항이 늘 때마다 가드가 하나씩 늘고 수렴하지 않는다(채권 18개가 수렴한 이유는 규칙이 yaml 에 있어서다).

---

## 1. 단계 0 — 인벤토리 (코드 0줄, 9/3)

가드 20개를 아래 표로 옮긴다. **이 표가 "일반화"의 실체다** — 발동 조건을 `tables / question / grounded / sql_has / sql_lacks` 다섯 축으로 못 쓰는 가드는 일반화가 안 되는 것이고 코드에 남긴다.

| 열 | 내용 | 채우는 방법 |
| :-- | :-- | :-- |
| 가드 | `ensure_fund_base_population` | 이름 |
| 기존 yaml 규칙 | `public_funds.yaml query_rules.기본모수` | `grep` — 같은 주제 규칙이 있으면 그 키. 없으면 "신설" |
| when.tables | `[public_funds]` | 가드 본문의 FROM 검사 |
| when.question | `not_any: [사모, 판매완료]` / `any: [몇 개, 개수]` | 가드의 질문 어휘 검사. `grounded: Country` 처럼 KG 접지 결과를 조건으로 쓰는 것도 여기 |
| when.sql | `lacks: [prvo_pbff_desc]` / `has: ["COUNT(*)"]` | 가드의 "SQL 에 아직 없으면" 검사 |
| action | `inject_where` / `replace_expr` / `replace_predicate` / `add_select` / `replace_order` / `remove_predicate` | 가드가 SQL 에 하는 일 |
| sql | `sale_yn='판매중' AND prvo_pbff_desc='공모'` | 확정식. `{code}`·`{key}`·`{col}` 자리표시자 허용(접지 결과 치환) |
| 원자성 | 교체 대상이 없으면 손대지 않음 / 주입 후 표식 | 12R 원자성 규칙 |
| 문항 | FND-030 · KG-005 … | docstring 의 ID |
| 현재 ✅ 영향 | 이 가드가 발동하는 ✅ 문항 수 | §2 섀도 로그에서 채움 |
| 판정 | A(슬롯) / B(표시·묶기, 코드) / C(위생, 코드) | |

산출물: `docs/guard_migration_inventory_2026-09-03.md`. 20행. 이 표는 그대로 제안서 부록 소재(runtime form 의 실물)다.

---

## 2. 단계 1 — 슬롯 스키마와 적용기 (코드, 9/3~9/4)

### 2-1. yaml 슬롯 (`ontology/enums/<domain>.yaml` `query_rules.<name>.enforce`)

```yaml
query_rules:
  기본모수:
    text: 집계·Top-N 은 sale_yn='판매중' AND prvo_pbff_desc='공모' 모수에서. 모수 8,969 를 답변에 밝힐 것
    enforce:
      when:
        tables: [public_funds]          # 이 테이블이 FROM/JOIN 에 있으면 (UNION 가지 각각 독립 판정)
        question: {not_any: [사모, 판매완료, 전체]}
        sql: {lacks: [prvo_pbff_desc]}
      action: inject_where
      sql: "sale_yn = '판매중' AND prvo_pbff_desc = '공모'"
      mark: BASEPOP                     # 주입 표식 — 사후조건과 코드 가드 침묵 판정용
  펀드단위:
    text: 펀드 개수는 (or_co, mtco) 단위. 클래스 수를 병기
    enforce:
      when: {tables: [public_funds], question: {any: [몇 개, 개수, 얼마나 많]}, sql: {has: ["COUNT(*)"]}}
      action: replace_expr
      from: "COUNT(*)"
      sql: "COUNT(DISTINCT or_co_xtn_itt_cd || {zeropad_mtco}) AS 펀드수, COUNT(*) AS 클래스수"
      mark: FUNDUNIT
  국가태그:
    triggers: [중국, 미국, …]
    text: 국가 질의는 prfd_attr_cds 태그로
    enforce:
      when: {tables: [public_funds], grounded: Country}
      action: replace_predicate
      target_columns: [fd_ivst_rgn_desc, ovrs_fd_desc]
      sql: "','||prfd_attr_cds||',' LIKE '%,{code},%'"
      mark: CTRYTAG
```

- `text` 는 그대로 프롬프트에 실린다(context form). `enforce` 는 프롬프트에 **싣지 않는다** — 적용기만 읽는다.
- `enforce: off` 이면 정의만 있고 발동 안 함(감사 결과 반영용).
- `when` 의 다섯 축 외의 조건은 허용하지 않는다. 필요하면 그 가드는 코드에 남긴다.

### 2-2. 로더 검증 (`loader.py`, 빌드 V8 성격)
- `action` 이 허용 목록에 있는가 · `sql` 의 컬럼이 그 테이블에 실재하는가 · `mark` 유일한가 · `from` 이 있으면 `replace_expr` 인가. 실패 시 로드 거부(V1~V7 과 같은 태도).

### 2-3. 적용기 (`guard.py` 신설 `apply_enforce(sql, q, tables, grounded, ctx) -> (sql, fired: list[mark])`)
- 선언 순서대로 1회 통과. UNION 은 가지별로 분해해 각 가지에 독립 적용 후 재조립(`sqlglot` 또는 기존 UNION 분기 함수 재사용).
- 원자성: `replace_*` 는 대상이 정확히 잡힐 때만, 아니면 손대지 않음. `inject_where` 는 WHERE 유무·괄호를 안전하게(기존 `ensure_or_group_parens` 로직 재사용).
- 발동한 `mark` 를 SQL 주석(`/*M:BASEPOP*/`)과 `PipelineResult.enforce_fired` 에 남긴다. `think_trace` 의 `[Guard]` 줄에 표기.
- **사후조건**(체인 끝): 발동했어야 할 규칙(`when` 참)이 최종 SQL 에 `mark` 로 남아 있지 않으면 → 재생성 1회 → 그래도 없으면 결정층 조립/거절. 12R 의 "표식 + 체인 끝 사후조건"을 슬롯에 일반화한 것.
- 호출 위치: `_apply_sql_guards` **맨 앞**. 기존 가드는 뒤에서 그대로 돈다(단계 2 섀도).

### 2-4. 코드 가드 침묵 조건
- 각 이전 대상 가드에 한 줄: `if 'M:<mark>' in sql: return sql, False`. 슬롯이 먼저 처리했으면 가드는 손대지 않는다. 가드 삭제는 §5.

---

## 3. 단계 2 — 섀도 실행 (9/4)

목적: 슬롯과 코드 가드가 **같은 결과**를 내는지, 슬롯이 **가드가 못 닿던 곳(교차 가지)** 에서 발동하는지 확인.

1. **raw SQL 기록** — 현재 probe 결과에 가드 전 SQL 이 없다(`raw_sql` 미저장). `qa_log`/`PipelineResult` 에 `raw_sql`(HCX 원문) 필드 추가(로그 전용, 응답 5필드 불변). 이것 없이는 재생 검증이 안 된다.
2. 문항: 15R ❌30 + ✅ 표본 30 + 공식 9 + 교차 25 = 94. 로컬 HCX 테스트 키로 1회 실행, `raw_sql`·`enforce_fired`·최종 SQL·가드 발동 목록 저장.
3. 판정표(가드×문항): `슬롯만 발동 / 가드만 발동 / 둘 다·동일 SQL / 둘 다·다른 SQL / 둘 다 미발동`.
   - **둘 다·다른 SQL** 이 0 이어야 전환 가능. 있으면 슬롯 `when`/`sql` 을 고친다(가드가 정답이라는 전제. 가드가 틀린 경우는 인벤토리에 기록).
   - **슬롯만 발동** = 이득 후보(교차 가지). 그 문항의 최종 답이 gold 와 맞는지 확인.
4. 산출물: `eval/enforce_shadow_2026-09-04.json` + 요약표.

---

## 4. 단계 3 — 전환 (항목 단위 커밋, 9/4~9/5)

순서는 15R 오답 기여도 순. **항목 하나 = 슬롯 켜기 + 가드 침묵 조건 + 회귀 테스트 + 커밋 하나.**

| 순위 | 가드 → 슬롯 | 닫는 오답 | 프리즈 전 |
| :-: | :-- | :-- | :-: |
| P0-1 | `ensure_fund_base_population` → `기본모수.enforce` | 교차 가지 모수 누락 | ✅ |
| P0-2 | `ensure_fund_distinct_count` + `ensure_fund_distribution_fund_count` → `펀드단위.enforce` | KG-025 · X9 등 클래스↔펀드 16건 | ✅ |
| P0-3 | `ensure_etf_index_canon` → `domestic_etfs.yaml` 지수 규칙 `.enforce` | CROSS-002 | ✅ |
| P1 | `ensure_fund_country_tag` · `ensure_fund_attr_tag` · `ensure_fund_type_axis` · `ensure_fund_mixed_type` · `ensure_fund_safe_grade_direction` | 축·태그 계열 | 여유 시 |
| P2 | `ensure_etf_base_population` · `ensure_fund_return_error_exclusion` · `ensure_fund_series_boundary` · `ensure_fund_estb_*` · `ensure_fund_holdings_template` · `ensure_fund_manager_ranking` · `ensure_fund_entity_count_ranking` · `ensure_etf_brand_token` · `ensure_fund_name_filter` | 나머지 A부류 | 프리즈 후 |

항목마다 통과 조건(전부):
```bash
export PYTHONIOENCODING=utf-8
./.venv/Scripts/python.exe -m pytest tests/test_snapshot_round6.py -q      # 동결선
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe eval/run_gold_check.py                          # 147/147
./.venv/Scripts/python.exe eval/run_paired.py --a guards --b enforce …     # 94문항, 값·축·단위·범위 4열
```
회귀선: 개별 조회 90% · 환각 9/9 · S8·R1 병기 · 답변형 62 CLARIFY/REFUSE 오발동 0. 하나라도 깨지면 그 항목은 되돌리고 인벤토리에 사유 기록.

커밋 본문 형식: `feat(enforce): <규칙명> 슬롯 전환 — 일반 규칙: … / 침묵 가드: ensure_… / 영향 범위: … / 섀도: 동일 N·슬롯만 M·불일치 0`.

---

## 5. 단계 4 — 가드 제거와 확산 (프리즈 후)

- 슬롯 전환 후 두 라운드 동안 침묵 가드가 한 번도 발동하지 않았으면 삭제. 발동 로그가 있으면 그 문항을 슬롯 `when` 에 반영 후 재확인.
- 채권·해외ETF 의 같은 주제 규칙에 `enforce` 를 붙인다(모수·대표행·정렬 축). 코드 추가 0.
- `07_리드_공통절.md` 2.3.2 ④ 와 5.3 에 결과를 쓴다: "규칙 N개를 runtime form 으로 옮겨 교차 경로 정답률 33%→X%".

---

## 6. 하지 말 것
- 가드를 먼저 지우고 슬롯을 켜는 것. 순서는 항상 슬롯 → 침묵 → (두 라운드 후) 삭제.
- `when` 에 다섯 축 밖의 조건을 넣는 것. 안 들어가면 코드에 남긴다.
- 슬롯 `sql` 에 문항별 리터럴. 값은 `{code}` 류 자리표시자로 접지 결과에서 온다.
- shared yaml·KG 빌더·ttl 변경. 이 작업은 enums `query_rules` 안에서만 끝난다.
- 전환 항목 두 개를 한 커밋에. 간섭은 항상 둘의 교집합에서 났다.

## 7. 산출물
- `docs/guard_migration_inventory_2026-09-03.md` (단계 0)
- `ontology/enums/*.yaml` `enforce` 블록 · `src/runtime/guard.py apply_enforce` · `loader.py` 검증 (단계 1)
- `eval/enforce_shadow_2026-09-04.json` + 요약 (단계 2)
- 항목별 커밋 + paired 결과 (단계 3)
