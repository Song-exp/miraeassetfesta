# 10R 수리 간섭 지도 — 2026-09-03

심사관 셋(`recheck_2026-09-03_round9.md` §③ · `kg_structure_probe_round6_2026-09-03.md` §③ ·
`gold_probe_2026-09-03_g2.md` §③)의 수정안을 **결정층 일반 규칙**으로 합친 지도.
온톨로지(`ontology/**` · `scripts/build_ontology.py`) · gold(`eval/questions_*.jsonl`) **무변경**.

세 심사관이 독립적으로 같은 계열을 짚었다. 개별 항목이 아니라 **가드의 구조적 결함 3종**을 먼저 닫는다.

---

## 0. 이번 라운드의 뿌리 3종

| 뿌리 | 정체 | 심사관 항목 |
| :-- | :-- | :-- |
| **①** 가드가 스스로 꺼진다 | 확정식 주입 가드의 술어가 `not <절이 있는가>` 라서, HCX 가 그 절을 **틀리게** 쓰면 가드가 자기를 끈다 | 재검 ③-1(부류 Z) · ③-3 · ③-4 · ③-9 · gold ③-B 6 |
| **②** 가드가 정상 SQL 을 기각한다 | 문장 전역 정규식이 UNION 가지·서브쿼리를 한 스코프로 본다 / 8R 괄호 가드가 우리 근거문서 원문을 기각한다 | KG 부류 Q · gold N1·N2 |
| **③** 클래스 개수 축이 틀렸다 | 개수·열거 축을 `mtco_itm_no`(운용 단위)로 잡았다. 정본은 `rptt_ksd_itm_no`(대표번호) | 재검 ③-B · 8R 보류 ③-1 |

---

## 1. 간섭 지도

| # | (a) 부류 → 일반 규칙 | (b) 닿는 층 / 충돌 가능 지점 → 고정할 회귀 테스트 이름 | (c) 경로가 바뀔 수 있는 기존 ✅ |
| :-: | :-- | :-- | :-- |
| **Z1** | 부류 Z — **확정식 가드의 발동 술어를 「절이 없는가」에서 「절이 확정식과 같은가」로.** 절이 있는데 확정식과 다르면 교체한다. 대상: 펀드/ETF 기본모수 · 유형 축 · 개별 조회 묶기 GROUP BY · 랭킹 대표행 GROUP BY | SQL 가드 `ensure_etf_base_population` · `ensure_fund_type_axis` · `ensure_fund_rank_representative` · `ensure_fund_lookup_grouping` / 충돌: 사용자 조건을 확정식이 덮어쓸 위험 → 확장 낱말(`_POP_WIDEN`·`_ETF_WIDEN`)로만 불개입 → `test_r10_guard_replaces_wrong_clause` | U7 · T6 · W5 · V7 · W10 · V14 · R7 |
| **Z2** | 부류 Z(랭킹) — 랭킹 대표행 가드의 **축소 분기에도** `COUNT(*) AS 클래스수` 를 주입하고 GROUP BY 축을 정본으로 교체한다(재검 ③-3 · ③-9 · gold ③-B 6). 이것이 `_fund_rank_answer` 의 `GROUP BY <정본식>` 리터럴 발동 조건을 결정적으로 만든다 | SQL 가드 `ensure_fund_rank_representative` 축소 분기 → 조립기 `_fund_rank_answer` / 충돌: 축 교체가 랭킹 값 자체를 바꾼다(펀드 수 3,040 유지 필수) → `test_r10_rank_group_axis_canonical` | V16 · Y1 · Y5 · R1 · T1 · V5 |
| **Q1** | KG 부류 Q — **SQL 검사기는 UNION 가지와 서브쿼리를 각각 독립 스코프로 본다.** 스코프를 넘어 매칭한 결과로 기각하지 않는다 | `pipeline.where_window_or_aggregate` (WHERE 종료어에 UNION 추가 — 이미 있는 `_WHERE_SEG` 재사용) · `guard.ambiguous_columns` (스코프 분리) / 충돌: 진짜 모호 컬럼을 놓칠 위험(실행 오류 → 재생성 경로 있음) → `test_r10_scope_split_no_false_reject` | KG-006 · AA4 · X19 · KG-033 |
| **N1** | gold N1 — **최상위 `A OR B AND C` 는 기각이 아니라 보정한다.** OR 를 AND 보다 강하게 묶어 `A AND (B OR C) AND D` 로 재괄호화한다. 8R 괄호 가드가 기각하던 문장이 우리 `enums:949` 원문이므로 자연어 피드백으로는 못 고친다 | SQL 가드 신설 `ensure_or_group_parens`(체인 맨 앞 — 뒤의 모든 AND 분해 가드가 이 형태를 전제한다) / 충돌: 의도적 `(A AND B) OR (C AND D)` 를 뒤집을 위험 → 괄호가 이미 있으면 불개입 → `test_r10_or_group_parens` | FND-009 · OFFICIAL-004 1차 |
| **N2** | gold N2 — **가드는 위반을 전부 모아 한 번에 돌려준다.** 첫 사유에서 return 하지 않는다. 재생성 예산 1회가 두 사유를 순차로 만나 소진되는 구조를 없앤다 | SQL 가드 `_sql_precheck` / 충돌: 사유 문자열이 길어져 재생성 프롬프트 희석 → 최대 3사유로 절단 → `test_r10_precheck_collects_all` | OFFICIAL-004 |
| **R1** | 재검 ③-B — **개수·열거 축은 `rptt_ksd_itm_no`.** 개별 조회 묶기 GROUP BY 를 `COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), <펀드키>)` 로. 🔴 **랭킹·분포의 `COUNT(DISTINCT 펀드키)` 는 불변**(3,040 유지) | SQL 가드 `ensure_fund_lookup_grouping` GROUP BY 식 / 충돌: `_lookup_answer` 의 대표번호 재접기와 이중 작동 → `test_r10_lookup_group_rptt` | W5 · U2 · U3 · Y11 · S1 4·5위 · T6 · R6 · S5 |
| **R2** | 8R 보류 ③-1 — `_LOOKUP_ROW_UNIT` 불개입은 **질문 낱말만** 본다. '클래스' 는 개수·열거를 묻는 말이라 묶기가 정답이고, '보수·수수료' 만 불개입 | SQL 가드 `ensure_fund_lookup_grouping` L1208 `and not m_grp` 삭제 + `_LOOKUP_ROW_UNIT` 에서 '클래스' 제거 / **R1 과 반드시 같이 집행**해야 W5 `rows` 7 유지 → `test_r10_lookup_class_no_shape` | T6 · R6 · S5 · V12 · V13 · W3 |
| **A1** | 재검 ③-A — 이름 검색 리터럴은 **KG 가 브랜드 라벨을 소비했더라도 「라벨+잔여」 결합형**으로 만든다. 결합형이 DB 에 실재할 때만(사용자가 브랜드를 안 쓰면 불개입) | Ground `residual_name_token` / 충돌: 결합형이 없는 이름은 종전대로 → `test_r10_name_anchor_prefix` | 🔴 T14 `rows` 4→2 · W9 3→2 (심사관 승인한 의도된 값 변경) · X18 · R4 · Y11 · U11 · S12 · V1 · W7 · Y15 |
| **E1** | KG 부류 E — 라우터가 붙이는 **설명서 항목 표식**(`_FUND_EXT_HINTS`)이 있는 질의는 `ensure_fund_lookup_grouping` 진입을 막고 **설정일 전용 확정식**(`MIN/MAX(e.estb_dt)` + 클래스수 병기)으로 교체 | SQL 가드 신설 분기(묶기 코드·산출 SQL 무변경) / 충돌: 묶기 경로 ✅ 전부 → 표식이 없으므로 SQL 동일 → `test_r10_estb_lookup_template` | AA5 · AA4 · KG-034 · Z9 · KG-033 · X19 · X20 |
| **T1** | KG 부류 T — ETF 지수·운용사 매칭은 `ref_base_index`·`ref_fund_mgmt_co` 를 확정식으로 쓴다. `cu_base_index`(95.5% 공백) · `cu_fund_mgmt_co`(54행에 상품명 전체)는 단독 근거로 쓰지 않는다 | SQL 가드 `ensure_etf_base_population` 옆 확정식 / 충돌: 해외 ETF 는 `cu_base_index` 가 정상 → 국내(`domestic_etfs`)에만 → `test_r10_etf_ref_index` | X7 · Z19 · AA22 · Z14 · AA21 · V7 · W10 |
| **S1** | gold N3 — 랭킹 기계 조립 머리줄에 **WHERE 의 사람이 읽는 조건**을 함께 굽는다(값 필터의 한글 라벨) | 조립기 `_fund_rank_answer` / 충돌: 머리줄 문자열 = 동결선 `answer_head` → `test_r10_rank_head_conditions` | FND-001 · FND-002 · UNANS-006 · 동결선의 랭킹 ✅ 전부 |
| **E2** | 재검 ③-2 — 묶기·랭킹 SQL 의 `COUNT(*) AS 클래스수` 는 **값 컬럼 술어와 무관하게** 기본모수 전체를 센다. 값 술어는 `HAVING`/집계 인자로 옮긴다 | SQL 가드 `ensure_fund_rank_representative`·`ensure_fund_lookup_grouping` / 충돌: `HAVING` 이동이 행 집합을 바꿀 위험 → 같은 술어면 행 집합 동일 → `test_r10_class_count_off_value_predicate` | S2 · Y3 · Y4 · R7 · S1 · V3 · W3 · R4 · V6 · V16 · Y1 · KG-023 · Z4 |
| **D1** | 재검 ③-6 — 금액 표시 열 문자열은 **천 단위 구분자까지 완성**해서 내보낸다 | 조립 `_cell`(표시 단위 접미 문자열 공통 자리 — 새 가드 만들지 않는다) / 충돌: 조립기의 재포맷과 이중 → 이미 콤마가 있으면 원문 사용 → `test_r10_amount_thousands` | U8 · Y16 · V7 · W10 · U13 · Y2 |
| **I1** | KG 부류 I — 값 검사 2회 실패 시 **질문의 낱말을 부정 술어로 뒤집지 않는다**. `NOT LIKE` 를 새로 만들지 않는다 | SQL 가드(값 검사 후처리) / 충돌: 정당한 제외 질의('MMF 빼고') → 질문에 제외 어휘가 있으면 존중 → `test_r10_no_inverted_predicate` | Z18 · AA9 · X16 · FND-006 |
| **N8** | gold N8 — **SQL 리터럴의 날짜도 기준일 가드가 검사한다.** 8자리 정수·`'YYYY-MM-DD'` 리터럴이 `gate.DATA_CUTOFF` 를 넘으면 그 조건을 제거한다 | SQL 가드 / 충돌: 만기(`mat_dt`) 는 미래가 정상 → 기준일 컬럼(`*_bas_dt`)에만 → `test_r10_future_date_literal` | FND-R02 · BND 만기 계열 전부(불개입 확인) |
| **H1** | KG 부류 E 부수 — **답변이 말한 축이 `retrieved_context` 헤더에 없으면 그 문장을 제거**한다 | 조립(`strip_*` 필터와 같은 자리) / 충돌: 정당한 서술까지 지울 위험 → 날짜·수치 단정 문장만 → `test_r10_unsourced_axis_sentence` | AA5 · 개별 조회 HCX 작문 경로 전부 |

---

## 2. 예측한 충돌 — 미리 정한 판정

1. **A1(접두 앵커)은 값을 바꾼다.** T14 `rows` 4→2 · W9 3→2. 재검 심사관이 §③-A 에서 명시적으로 승인했고
   "회귀가 아니라 교정" 이라고 판정했다. 동결선이 이 둘을 담고 있으면 근거를 적고 스냅샷을 갱신한다.
2. **R1 과 R2 는 반드시 같은 커밋.** R2 단독이면 W5 `rows` 7→6(8R 보류 사유), R1 이 축을 rptt 로 바꾸면 7 유지.
3. **Z2 의 GROUP BY 축 교체는 랭킹 모수를 건드리면 안 된다.** 교체 대상은 `or_co_xtn_itt_cd` 를 포함한
   펀드단위 GROUP BY 뿐이고, `_FUND_KEY_EXPR` 자체는 그대로 쓴다(rptt 로 바꾸지 않는다 — 3,040 유지).
4. **N1 은 체인 맨 앞.** 뒤의 모든 가드가 `split_conjuncts`(최상위 AND 분해)를 쓰므로, 최상위 bare OR 가
   남아 있으면 그 가드들이 조건을 잘못 자른다. 맨 앞에서 한 번 접으면 뒤가 전부 안전해진다.

---

## 3. 구현하지 않는 것 (보고만)

- **온톨로지 관련 보고 3종**(재검 ③-14 · KG 별도 보고 2건) — 세 심사관 전원이 "온톨로지 변경 요구 0건" 명시.
- **gold 파일 오류 5건**(gold ④-1~④-5) — 리드 확인 대기. 파일 무변경.
- **정본 펀드 수 3,040 vs 1,919** — 6라운드 gold 통과분. 축 변경은 이번 라운드 밖.

---

## 3-bis. 집행 결과 (구현 종료 시점 기록)

| 항목 | 상태 | 커밋 | 회귀 테스트 | 예측한 충돌이 실제로 났는가 |
| :-- | :-- | :-- | :-- | :-- |
| N1 · Q1 · N2 (뿌리②) | 구현 | `bbcbec7` | `test_r10_or_group_parens` · `test_r10_scope_split_no_false_reject` · `test_r10_precheck_collects_all` | 없음 |
| Z1 · Z2 · E2 · ③-5 (뿌리①) | 구현 | `6870e74` | `test_r10_guard_replaces_wrong_clause` · `test_r10_rank_group_axis_canonical` · `test_r10_class_count_off_value_predicate` | **예측대로** V16 이 조립기 경로로 이동(③-3 이 요구한 변경) |
| R1 · R2 (뿌리③) | 구현 | `89cf5d5` | `test_r10_lookup_group_rptt` · `test_r10_lookup_class_no_shape` · `test_r10_lookup_answer_only_for_name_lookup` | **예측 밖 2건** — `_has_name_filter` 가 ⓐ 리터럴 안의 괄호로 그룹 범위를 놓치고 ⓑ 연결식 컬럼을 못 봐서, 이름 필터 중복 주입(S5)과 태그 질의 오판(KG-021)이 났다. 둘 다 그 함수에서 닫았다 |
| A1 접두 앵커 | 구현 | `7aa7256` | `test_r10_name_anchor_prefix` | **예측대로** R4 6→2 · W9 3→2 · X18 20→10 (심사관 ③-A 승인분) |
| D1 자릿수 · N8 기준일 리터럴 | 구현 | `d64892e` | `test_r10_amount_thousands` · `test_r10_future_date_literal` | 조립기 3곳의 `int()` 파싱이 콤마에 걸렸다 — 전부 콤마 허용으로 고침 |
| I1 부정 술어 · H1 미조회 축 | 구현 | `9244216` | `test_r10_no_inverted_predicate` · `test_r10_unsourced_axis_sentence` | 없음 |
| T1 ETF 지수 · S1 머리줄 조건 | 구현 | `fa5c137` | `test_r10_etf_ref_index` · `test_r10_rank_head_conditions` | 없음 (지수 확정식은 모수 가드보다 **앞**이어야 한다 — 순서 조정) |
| E1 설정일 확정식 | 구현 | `e93fe2d` | `test_r10_estb_lookup_template` | 없음 (묶기 코드 무변경 — 예측대로 등급·클래스수 계열 불변) |
| ③-7 TOP n · gold 5 보수 축 | 구현 | `6018609` | `test_r10_dialect_top_rewrite` · `test_r10_fee_is_rank_axis` | 없음 |
| N6 · ③-11 · gold 1·4 | 구현 | `7b8fb63` | `test_r10_zero_is_display_rule` · `test_r10_etf_scope_note` · `test_r10_manager_template_not_for_pinned_org` | 술어의 **리터럴이 질문에 있으면 존중** 조건이 빠져 지수 절이 지워졌다 — 추가 |
| ③-10 근접 후보 · N7 행 전사 | 구현 | `990c35a` | `test_r10_nearest_candidates_and_rows_answered` | 축소 하한을 3자로 고정하니 3자 토큰의 오타 회복이 죽었다 — 토큰의 2/3(최소 2자)로 |

### 보류 (근거 명시)

| 항목 | 보류 사유 |
| :-- | :-- |
| 재검 ③-B 의 **S1 4·5위 중복** | rptt 축은 개수·열거에만 쓰기로 한 경계(랭킹 `COUNT(DISTINCT 펀드키)` 불변)의 반대쪽이다. 랭킹 GROUP BY 를 rptt 로 바꾸면 정본 펀드 수 3,040 → 1,919 로 움직여 R1·T1·V5 가 흔들린다 |
| 부류 T 의 **운용사 축**(`ref_fund_mgmt_co`) | 한글 브랜드 ↔ 영문 정식명 매핑이 필요하고, DB 실측(`LIKE 'Samsung%'` 265/268)이 심사관 수치(240/243)와 어긋난다. 근거 확인 후로 |
| gold ③-B 3 **2차 실패 시 최소 SQL 대체 실행** | "가드가 만든 최소 SQL" 의 정의가 없어 임의 완화가 된다(§9 조건 완화 금지와 충돌). N1·N2 로 무응답 원인 두 개가 닫혔으므로 남은 폭을 다음 라운드에 재측정 |
| gold ③-B 22 **보수 4항목 합계 주입** | SELECT 재작성 폭이 커 랭킹·묶기 두 경로와 동시에 부딪힌다 |
| N5 **교차 경로 펀드 가드**(CROSS-001) | 펀드 가드 전부가 `union` 을 불개입 사유로 쓴다. UNION 가지 단위 적용은 가드 10여 개의 진입 조건을 한꺼번에 바꾸는 일이라 한 라운드를 따로 써야 한다 |
| N4 서수 ORDER BY 재검증 · G-D 되묻기 · G-E 형태소 분해 등 | 값 기여가 작거나 폭이 커서 이번 예산 밖 |
| 온톨로지 보고 3건 · gold 파일 오류 5건 | 경계 규정대로 **구현하지 않음** |

**③-13(미검증 규칙) 확인 결과**: `0행 원인 절 제거` 마커는 죽은 코드가 아니다 —
`drop_unquestioned_numeric_clause` 는 살아 있고 회귀 테스트(`test_r6_O_numeric_clause_rerun`)도 통과한다.
발동 조건이 **0행 + 질문에 없는 숫자 임계값 + 그 절 단독으로도 0행** 세 개가 동시에 맞아야 해서 실제 라운드에
잘 안 걸릴 뿐이다. 이번 라운드에 HAVING 으로 옮겨 간 값 술어까지 보도록 범위를 넓혔다.

## 4. 검증 절차 (항목마다)

```bash
export PYTHONIOENCODING=utf-8
./.venv/Scripts/python.exe -m pytest tests/test_snapshot_round6.py -q   # 동결선
./.venv/Scripts/python.exe -m pytest -q                                 # 전체
./.venv/Scripts/python.exe eval/run_gold_check.py                       # gold 147/147
```
KG·ttl·yaml 무변경 → `build_ontology.py` 재실행 대상 아님.
