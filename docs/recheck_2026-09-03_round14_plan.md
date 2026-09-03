# 14라운드 수리 간섭 지도 — 2026-09-03

출처 §③ 합본: `docs/recheck_2026-09-03_round13.md`(10항) · `docs/kg_structure_probe_round8_2026-09-03.md`(18항) ·
`docs/gold_probe_2026-09-03_g4.md`(24항).

기준선(수리 전 실측): `pytest -q` 406 passed · `eval/run_gold_check.py` 147/147 · 동결선 `tests/test_snapshot_round6.py` 통과.

> 🔴 이 문서의 「보류」는 **구현하지 않았다는 뜻**이다. 12R 의 사고(계획서엔 보류, 실제로는 배포 → S3 회귀)를
> 되풀이하지 않기 위해 구현/보류를 항목마다 명시하고, 라운드 끝에 실제 커밋과 대조한다.

---

## 1순위 — 환각 방지 축 (`UNANS-001`)

| (a) 부류 → 일반 규칙 | (b) 닿는 층 / 충돌 가능 지점 → 회귀 테스트 이름 | (c) 경로가 바뀔 수 있는 ✅ 문항 |
| :-- | :-- | :-- |
| **P1-a 부류 Z″ — 사용자 브랜드 조건 소실 금지(상품명 축)**. ETF 상품명 필터가 걸린 SQL 에 질문의 **DB 실측 브랜드 접두**(`domestic_etfs.pd_abrv_nm` 첫 토큰, 5행 이상)가 하나도 안 남아 있으면 그 조건을 되돌려 주입한다. 0행이면 되묻기 경로가 받는다 — 조건이 지워진 목록은 답이 아니다 | SQL 가드(체인 끝 사후조건). 충돌: `ensure_etf_base_population`(모수 주입) · `ensure_etf_index_canon`(지수 확정식이 이름 절을 OR 로 감쌈) · `_suggest_similar_products`(0행 되묻기) → `test_round14_repairs.py::test_etf_brand_token_postcondition` | ETF 상품명 질의 전부 — `AA22`·`U8`·`V7`·`W10`·`OFFICIAL-004`(이름 LIKE 에 브랜드 없음 → 불개입이어야 한다) |
| **P1-b ③-2 — 정확일치·유사 판정은 공백 정규화 후에.** `_suggest_similar_products` 가 `pd_nm/pd_abrv_nm` 의 **공백 무시 LIKE 리터럴**도 조회 리터럴로 인정한다 | Ground/조립기(0행 경로). 충돌: `_zero_row_reason`(펀드 경로 · 되묻기가 있으면 진단을 겹치지 않는 기존 분기) → `::test_suggest_similar_reads_spaceless_like` | `OFFICIAL-NA-003`(현재 ✅ · 등호 경로 불변) · `UNANS-002`~`005` |
| **P1-c ③-18 — 금지 문형 제거는 반환 직전 한 자리.** `strip_disclaimer` 를 「권유·전망」 문형까지 넓히고 **기계 조립·전사 강제·Refuse 경로에도** 건다 | 답변 조립기(`answer_question` 반환 직전). 충돌: `strip_false_hedge`(같은 자리에서 거짓 유보 제거 — 두 가드가 같은 문장을 반대로 읽지 않도록 문형 사전을 공유) → `::test_strip_disclaimer_advice_forms` | 면책 0건을 이미 달성한 109문항 전부(문장이 더 지워지면 안 된다) |
| **P1-d ③-20 — 폐기 컬럼은 SELECT 에서도 폐기.** `ensure_etf_mgmt_canon` 이 WHERE·GROUP BY 뿐 아니라 SELECT 목록의 `cu_fund_mgmt_co` 도 정본 `ref_fund_mgmt_co` 로 바꾼다 | SQL 가드. 충돌: `ensure_amount_eok_columns`(SELECT 항목 수 변화 없음 — 치환만) · 위치 ORDER BY(항목 수 불변이라 안전) → `::test_etf_mgmt_canon_select_list` | `AA21`·`Z14`·`KG-025` ETF 절(정본 축 240 = gold) |

## 2순위 — 우리 가드가 만든 사고 (부류 AC)

| (a) 부류 → 일반 규칙 | (b) 닿는 층 / 충돌 → 회귀 테스트 이름 | (c) 경로가 바뀔 수 있는 ✅ 문항 |
| :-- | :-- | :-- |
| **P2-a ③-3 — 정렬축 감싸기는 SELECT 항목 단위.** `_wrap_sort_col` 이 SELECT 를 항목으로 분해해 ⓐ 항목 전체가 그 컬럼(테이블 별칭 포함)이면 `agg(col) AS col` ⓑ 항목이 식이면 **항목 전체**를 `agg(<식>) AS <원별칭>` ⓒ 감쌀 수 없으면 보정 포기(원 SQL 반환). 부분 치환 금지 | SQL 가드 `_wrap_sort_col`·`_reagg_class_axis`·`_wrap_order_by_col`. 충돌: `ensure_fund_rank_representative`(위치 ORDER BY 를 유지해야 함) · `ensure_amount_eok_columns`(별칭이 바뀌면 표시 열 이름이 바뀐다) → `::test_wrap_sort_col_expression_item`·`::test_wrap_sort_col_table_alias` | `FND-003`·`FND-004`·`FND-009`·`S1`·`R7`·`U14`·`V16`·`Y1`(랭킹 전부) |
| **P2-b ③-4 — SELECT 목록 편집 가드는 단일 SELECT 에서만.** 공통 헬퍼 `_single_select(sql)`(공백 제거 첫 토큰이 `SELECT` · `UNION/EXCEPT/INTERSECT` 없음)을 SELECT 편집 가드 전부에 건다 | SQL 가드 전반(`ensure_amount_eok_columns`·`ensure_risk_name_column`·`ensure_grade_select_column`). 충돌: **P4-a(UNION 가지별 적용)와 정면으로 만난다** — 가지 분해가 들어가면 각 가지가 단일 SELECT 이므로 헬퍼는 가지에 대해 참이 된다(순서: P2-b 먼저, P4-a 가 그 위에 얹힌다) → `::test_amount_eok_skips_union` | 모든 교차질의 — `CROSS-001`~`003`·`X8`·`X9`·`KG-025`·`KG-026` |
| **P2-c ③-5 — 위치 `ORDER BY` 는 SELECT 열 수와 대조.** 실행 전 검사에 범위 검사를 넣고, 재생성 피드백에 「위치 대신 이름·별칭」을 명시 | SQL 가드(`validate_sql`) + 재생성 루프. 충돌: `_fund_sort_target`(위치 표기를 읽어 랭킹 컬럼을 찾는다 — 범위 밖이면 이미 None) → `::test_order_by_position_out_of_range` | 위치 ORDER BY 를 쓰는 랭킹 전부(`FND-005`·`FND-010`·`KG-008`) |
| **P2-d 재검 ③-1 — 역조회 운용사 코드는 등호로 쓰지 않는다.** ⓐ 이름 리터럴이 이미 브랜드 어간을 품으면 코드 술어를 **제거** ⓑ 아니면 브랜드 어간 역조회로 나온 **코드 전부의 `IN`**(DB 실측 · 역외 종별은 질문이 역외를 요구할 때만) | Ground `mgmt_code_from_question` → SQL 가드. 충돌: `ensure_fund_name_filter`(이름 토큰 사후조건) · `_offshore_sibling_note`(역외 분리 고지 — 코드 목록에 역외가 들어가면 고지가 꺼진다) → `::test_mgmt_code_predicate_dropped_when_name_has_brand`·`::test_mgmt_code_predicate_in_list` | `T7`·`S4`·`T8`·`U1`·`U3`·`V13`·`W1`·`Y8`·`Y10`(단일코드 브랜드) · `R5`·`S9`·`T11`(역외 분리 고지) |
| **P2-e 재검 ③-3 — 억원은 SQL 이 구운 열을 조립기가 그대로 쓴다** | 조립기 `_lookup_answer` 금액 포맷. 충돌: `ensure_amount_eok_columns`(열 이름 규약) · `_hide_answer_columns`(원값 숨김) → `::test_lookup_answer_uses_baked_eok` | 회귀 감시선 `Y8`(876 불변) · `U15`·`W4`·`U5`·`V15` |

## 3순위 — 심사관이 실측으로 확정한 것 (보류 해제)

| (a) 부류 → 일반 규칙 | (b) 닿는 층 / 충돌 → 회귀 테스트 이름 | (c) 경로가 바뀔 수 있는 ✅ 문항 |
| :-- | :-- | :-- |
| **P3-a KG ③-5 / AA16 — `FROM public_funds` 집계·랭킹에 기본모수를 사후조건으로 *추가*.** `SUM(CASE WHEN <기본모수> THEN 1 ELSE 0 END)` 로 모수를 흉내 낸 SELECT 는 모수 절로 승격한다. **`where` 축소가 아니라 추가**라 `S5`·`W5`·`X18` 의 `where` 는 한 글자도 안 바뀐다 | SQL 가드 `ensure_fund_base_population(post=True)`. 충돌: `ensure_fund_entity_count_ranking`(이미 `펀드수`/`클래스수` 를 심는다 — 축 목록에 수탁사·판매사 코드 추가) → `::test_base_population_group_by_entity`·`::test_entity_count_axis_trustee` | 🔴 동결선 `S5`·`W5`·`X18` · `R1`·`T1`·`V5`·`R2`·`Y6` |
| **P3-b KG ③-7 / X12 — 역외 포함 요구는 `ofsfd_yn`·역외 법인코드 축으로 집행하고, 뺐으면 뺐다고 적는다** | SQL 가드(P2-d 와 같은 자리) + 조립기(`_offshore_sibling_note`). 충돌: P2-d 의 코드 `IN` 목록 · `_count_answer` 머리줄 → `::test_offshore_included_when_asked` | `S9`·`T11`·`KG-031`(현재 분리 고지 ✅) · `U11`·`Y11` |
| **P3-c gold ③-24 / FND-008 — 자산군 축은 DB DISTINCT 실측으로 `IN` 확정.** 질문 낱말을 **접두**로 갖는 `zrin_btyp_nm` 값 집합으로 `IN` 을 기계 확정하고 HCX 의 `=`·`LIKE` 는 교체. 값 목록은 매번 DB 에서 뽑으므로 하드코딩·온톨로지 변경 아님 | SQL 가드 `ensure_fund_type_axis`. 충돌: `ensure_fund_mixed_type`(혼합형 확정식 — 「채권형」 접두 집합에 `채권혼합형` 이 들어가면 두 가드가 같은 낱말을 반대로 읽는다 → 접두 집합에서 `*혼합형` 제외) → `::test_type_axis_prefix_in` | `FND-009`·`Y7`·`R1`·`V5`·`Z10`·`AA6` |

## 4순위 — 남은 주력

| (a) 부류 → 일반 규칙 | (b) 닿는 층 / 충돌 → 회귀 테스트 이름 | (c) 경로가 바뀔 수 있는 ✅ 문항 |
| :-- | :-- | :-- |
| **P4-a KG ③-1 — 가드 체인을 UNION 가지 단위로.** 확정식 주입·컬럼 정본화·기본모수 사후조건·펀드단위 집계 교체를 가지마다 그 가지의 `FROM` 기준으로 1회씩 | SQL 가드 전반. 충돌: **P2-b**(단일 SELECT 판정) — 가지 분해기가 각 가지를 단일 SELECT 로 넘기므로 두 규칙이 같은 헬퍼를 공유해야 한다. `ensure_limit`·`ensure_default_topn`(문장 전체 기준 — 가지에 걸면 안 됨) → `::test_union_branch_guards` | `CROSS-003`·`X8`·`X9`·`KG-025`·`KG-026`·`Z13`·`X15` |
| **P4-b X8 — 지수·벤치마크 이름 비교도 공백 무시.** `ensure_spaceless_name_match` 의 대상 컬럼에 `bmrk_nm` 을 더한다(같은 목적 가드 신설 금지) | SQL 가드. 충돌: `ensure_etf_index_canon`(`ref_base_index` 는 이미 정본 GLOB 확정식) → `::test_spaceless_bmrk_nm` | `X9`·`KG-026` |
| **P4-c KG ③-3·4 / KG-008 — 가드 주입 별칭 유일화 + 랭킹은 기계 조립.** 가드가 심는 `펀드수` 가 HCX 별칭과 충돌하면 접미(`__g`)로 유일화하고, 조립기는 가드 별칭만 값 축으로 인정 | SQL 가드 + 조립기. 충돌: `_manager_rank_answer`(같은 템플릿 축) · `label_code_columns`(헤더명 기준) → `::test_entity_count_alias_unique` | `S11`·`R2`·`T1`·`V5` |
| **P4-d KG ③-2 / KG-017 — 확정식은 *같은 컬럼* 잔여 술어도 걷는다** | SQL 가드 `ensure_fund_attr_tag`. 충돌: `Z5` 를 살린 「타 컬럼」 판(같은 함수 — 조건만 넓힌다) → `::test_attr_tag_same_column_residual` | `Z5`·`KG-018` |
| **P4-e KG ③-9 / X22 — 집계 1행의 `0` 은 '0개' 다** | 조립기 `_zero_count_answer`. 충돌: `ensure_positive_count_answered`(양수 판) → `::test_zero_count_with_extra_columns` | `U3`·`X17`·`OFFICIAL-NA-002` |
| **P4-f 재검 ③-2 / 부류 E — 개별 조회·펀드단위 랭킹에도 `COUNT(*)` 모수 분리** | SQL 가드 `ensure_fund_lookup_grouping` 끝에서 `_class_count_off_value_predicate` 호출 → `::test_lookup_grouping_class_count_off_value` | `U15`·`U1`·`S4`·`Y10`·`W11`·`V2`·`Y9`·`Y15`(SQL 이 안 바뀌어야 한다) |
| **P4-g 재검 ③-4 / Y14 — 조립기 발동 판정을 「값 컬럼 존재」로** | 조립기 `_lookup_answer` 발동 판정 → `::test_lookup_answer_fires_with_extra_columns` | `V12`·`W5`·`T6`·`U16`·`R4`·`U15`·`S12`·`W1` |
| **P4-h KG ③-8 / Z16 — 같은 `label_official` 의 `or_co` 코드는 전부 `IN`** (실측 중복 1건) | Ground(P2-d 와 같은 자리) → `::test_label_official_duplicate_codes` | 운용사 질의 전부 |

## 보류(구현하지 않음) — 사유 명시

- **gold ③-6·③-8(CROSS-001·002 환각 컬럼 기계 치환 · 지수 JOIN ON)** — 재생성 루프 구조 변경이 필요하고 P2-b/P4-a 의 UNION 분해와 같은 자리를 만진다. 한 라운드에 두 구조 변경을 겹치면 12R 사고가 재현된다.
- **gold ③-10~③-17·③-19·③-21~③-23** · **KG ③-6·③-11~③-18** · **재검 ③-5~③-8** — 서술 계열(값 불변). 1~3순위와 P4-a~h 를 끝낸 뒤 남은 예산으로만.
- **재검 ③-10 정본 축(3,040 vs 1,919)** — 리드 판단 대기(심사관도 구현안 아님으로 명시).
- **gold jsonl 수정** — 금지(리드 확인 대기).

## 온톨로지 무변경 확인

`ontology/**` · `scripts/build_ontology.py` 는 이 라운드에서 한 글자도 바꾸지 않는다. P3-c 는 `zrin_btyp_nm`
DISTINCT 를 **런타임에 DB 에서 뽑아** 쓰므로 온톨로지 밖이다.
