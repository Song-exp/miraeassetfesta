# 채권 QA r1 수리 계획 — 간섭 지도 (에이전트 A · 2026-09-06 · 브랜치 qa/bonds-r1)

> 지시서: `docs/bonds_2026-09-06_round1.md` §③(가) BA~BP(🔴) · BM~BO(🟡). 실측 원본 `eval/probe_bonds_2026-09-06_r1.json`.
> 기준 HEAD: `9afb3aa`(a3bd4f0 F1~F8 · 6a5bb63 라운드 32 포함). 서버는 `db17e07`.
> 재현 방법(HCX 0회): 서버 think_trace 의 `[Plan] SQL 생성` 원문(재생성분은 2차 SQL)을 가짜 플래너로 `answer_question` 에 재투입.
> 스크립트는 세션 스크래치(`replay_all.py`)에 있고 87문항 기준선 `base.json` 을 떠 두었다 — 수리 뒤 같은 스크립트로 ✅ 51문항의 답변·SQL 을 대조한다.
> 격리 워크트리엔 DB 가 없다 → `DB_PATH=<원본 트리>/data/financial_products.db` 환경변수로 연결(loader.db_path 가 읽는다). 동결선 1 passed 확인.

## 0. HEAD 재현 결과 — 무엇이 이미 닫혔고 무엇이 남았나

| 부류 | 문항 | HEAD 재현(서버 1차 SQL 재투입) | 판정 |
| :-: | :-- | :-- | :-- |
| BA | A-043 · D-027 | F1 값-컬럼 교정은 채택되지만 `TRIM(std_pd_scls_nm)='국고채'` 단독으로 남아 **290 / 48** (gold 295 / 49). `ensure_ktb_kind` 는 SQL 에 '국고채권' 문자열이 있으면(A-043 의 OR 가지) ④ 분기를 건너뛰고, D-027 은 체인 시점엔 `std_pd_mcls_nm='국고채'` 라 어느 패턴에도 안 걸린다 | **미착수** |
| BB | A-008 · S-010 | A-008 3,059(gold 33) · S-010 지방채/STRIPS 5행(gold 회사채 5등급). `restore_kind_breadth` 는 좁힘만 잡고, `ensure_kind_filter` 는 종류 컬럼 존재만 본다 | **미착수** |
| BC | D-019 | 1차 SQL(`bd_nm` 환각) 기각 → 재생성 SQL(`pd_nm LIKE OR bd_knd IN ('전환사채','교환사채')`)은 6a5bb63 `fix_structure_kind_literal` 이 판정식으로 바꿔 통과 — **재생성 경로로 HEAD 에서 닫힘**(1차 SQL 만 반복하는 #87 형이면 여전히 오거절이지만 서버 실측은 2차가 달랐다) | HEAD 로 이미 닫힘(재생성 1회 비용은 남음) |
| BD | D-037 · D-045 · D-010 · S-004 | 넷 다 HEAD 에서도 기각→오거절: `IN TRIM('AA'), TRIM('AA+')` · `IN (...), TRIM('AA'), TRIM('AAA'))` · `LIKE '%/코/%)` 따옴표 불균형 · `GROUP BY pd_no, mtco_itm_no`(drop_unknown_select_columns 는 SELECT 만) | **미착수** |
| BE | D-010 | BD 뒤에도 `pd_nm LIKE '%코코본드%'` 만 남아 0행이 될 것 — 구조 판정식(은행 3종 + 위험등급 1~3) 주입 필요 | **미착수** |
| BF | C-016 · BR-X05 | C-016 목록 215종목 그대로 · X05 는 `_RISK_CUE` 에 `국공채|회사채` 가 들어 있어 되묻기 불발 | **미착수** |
| BG | D-020 | `_RECO_Q`/`_RANK_Q` 불발 → 1등급 코코본드 1위 그대로 | **미착수** |
| BH·BI | D-025 | `COUNT(DISTINCT pd_no), AVG(applied_yield)` 1행이 HCX 산문으로 넘어감 · '16' 단독 그대로 | **미착수** |
| BJ | S-007 | `(16 OR 11) … LIMIT 2` 6등급 국민주택 2행 그대로 | **미착수** |
| BK | BR-X10 | `bd_intp_tcd IN ('할인채','복리채','단리채')` 2,829 목록 그대로 | **미착수** |
| BL | UT-094 | F1 은 채택되지만 창 강제 불발 → 1,420종목 3.79%(gold 2,672종목 3.651%). 마커 `/*M:BONDPOP*/` 가 WHERE 본문 안(LIMIT 앞·또는 절 사이 — D-025 는 `… 20290824) /*M:BONDPOP*/ AND applied_yield > 0 …` 처럼 **절 중간**)에 붙어 `_WHERE_BODY` 소비자들이 `m`·`bondpop` 을 컬럼 토큰으로 읽는다 | **미착수** |
| BM | D-006 · D-036 · D-024 | 정렬·집계 없는 목록엔 BONDPOP 슬롯 불발 → 386/386/2,954 그대로 | 미착수(🟡) |
| BN | D-012 | `bd_intp_tcd IN ('이표채','복리채')` 가 WHERE 에 있어 `ensure_coupon_type_split` 불개입 → 17,505 | 미착수(🟡) |
| BO | 10건 | — | 미착수(🟡) |
| BP | 시간 | ②③④ 미착수. `HCXResult.retries`·`rate_limit` 은 client 가 이미 계산하지만 planner→pipeline 으로 올라오지 않아 trace 에 없다 | **미착수** |

## 1. 간섭 지도 — (a) 부류→일반 규칙 | (b) 닿는 층·기존 함수·충돌 위험점 → 회귀 테스트명 | (c) 경로가 바뀔 수 있는 ✅ 문항

회귀 테스트는 전부 `tests/test_round33_bonds_r1.py` 한 파일에 부류별로 모은다(발동/불개입 짝). 기존 함수 확장 원칙 — 새 가드 신설 0.

| # | (a) 부류 → 일반 규칙 | (b) 닿는 층 / 충돌 가능 지점 → 회귀 테스트 | (c) 영향 가능 ✅ |
| :-- | :-- | :-- | :-- |
| **BL** 🔴 (맨 먼저 — 다른 항목의 WHERE 판독이 이 위에 선다) | `_WHERE_BODY` 를 읽는 자리 공통으로 `/*M:\w+*/` 슬롯 마커를 본문에서 먼저 벗긴다 — 마커는 컬럼이 아니다. 마커는 LIMIT 앞뿐 아니라 **절 사이**에도 온다(D-025) | `enforce_relative_window`(others 토큰 집합) · `_effective_mat_window`(머리줄 창 표기 — `^mat_dt BETWEEN …$` 정규식이 꼬리 마커에 실패) · `align_threshold_operator`(F3). 한 곳(`_where_body_parts` 류 헬퍼)에서 벗기고, 재조립 시 마커를 WHERE 끝에 되붙여 `marked_conjuncts`·슬롯 짝 가드의 침묵 조건을 깨지 않는다. 충돌: `_flatten_and_groups` 가 마커를 품은 괄호 묶음을 못 펴는 경우 → 벗기기를 flatten **앞**에 → `test_BL_window_marker_before_limit` · `test_BL_window_marker_mid_where` · `test_BL_effective_window_with_marker` · `test_BL_threshold_with_marker` · 기존 `test_round31 test_issue_year_window` | D-004 · D-007 · D-037 · D-040 · D-041 · D-055 · BR-X08 · D-025(창 머리줄) — 창 값은 그대로여야 하고 머리줄 표기만 늘 수 있다 |
| **BA** 🔴 | 리터럴 `'국고채'` 등호는 컬럼(std_pd_mcls_nm·std_pd_scls_nm)을 불문하고 국고채 확정식으로 치환하며, SQL 에 확정식 문자열(`_KTB_FILTER`)이 이미 있으면 불개입(멱등). F1 채택 뒤 `ensure_ktb_kind`·`ensure_kind_filter` 를 한 번 더 돈다 | `ensure_ktb_kind` ④ 분기의 `"국고채권" not in sql` 게이트가 A-043(OR 가지에 '국고채권')을 막는다 → 게이트를 `_KTB_FILTER not in sql` 로. `ktb_head_is_gov`(A-042·A-045 '국공채 머리명사')는 그대로 선행. `_bond_count_answer` 의 국고채 병기는 `_MCLS_EQ` 만 보므로 무관 → `test_BA_scls_eq_any_column_to_ktb` · `test_BA_idempotent_when_filter_present` · `test_BA_gov_head_untouched`(A-042 문형) · `test_BA_refix_after_value_column`(A-043 → 295 · D-027 → 49) | D-029 · A-042 · A-044 · A-045 · D-007 · UT-095(은행채 — 불개입) |
| **BB** 🔴 | 질문의 종류 확정식이 정확히 하나(F)이고, WHERE 최상위 절 중 **종류·이름·발행사 컬럼만으로 이뤄진 절**(bd_knd·std_pd_mcls_nm·std_pd_scls_nm·pd_pbcm·pd_nm)의 종류 리터럴 집합이 F 와 다르면 그 절을 F 로 교체(과확장·모순 둘 다). 다른 컬럼(pd_risk_gcd·crd_grd·mat_dt…)이 섞인 절은 불개입 | `restore_kind_breadth` 확장(좁힘 분기 유지). 충돌 ①: BE 가 주입하는 구조 판정식은 `pd_risk_gcd` 를 품어 규칙상 제외 — 그래도 순서를 BB → BE 로 고정. 충돌 ②: `ensure_ktb_kind` ②(대분류 IN 국공채·특수채 → KTB)와 겹침 — 결과 동일, BB 가 먼저 KTB 를 넣으면 ktb 가드는 불개입. 충돌 ③: `ensure_credit_backstop`(정부보증 질의)의 OR 층은 질문에 종류 낱말이 없어 F 가 비므로 불개입 — D-014·D-026 확인. 불개입: `_KIND_NEG_Q` · 종류 낱말 2개 이상(A-042·A-043) · 하위 종류 낱말 직접 언급 → `test_BB_overexpanded_in_list_replaced`(A-008 → 33) · `test_BB_contradicting_mcls_replaced`(S-010) · `test_BB_untouched_two_kinds` · `test_BB_untouched_structure_predicate` · `test_BB_untouched_backstop` | D-037·D-045·BR-P09·D-028(회사채 = 그대로) · D-014·D-026(보강 OR — 불개입) · UT-095 · A-059(부동산투자회사채 — 종류 낱말 아님) |
| **BI** 🔴 | 최상급 없는 '안전한' = `pd_risk_gcd IN ('15','16')`(없으면 주입 · '16' 단독이면 완화) · 6등급 없는 종류를 지목한 최상급 안전 질의에서 위험 절이 통째로 없으면 폴백 IN ('15','16') 주입(현행 `return sql, False` 사각 — S-010) | `ensure_top_safety` 확장(역방향). 충돌: `strip_fabricated_risk_filter` 는 `_RISK_VOCAB`('안전')이 있으면 불개입이라 서로 안 겹침. `_TOP_SAFE_Q` 판정은 그대로 → `test_BI_plain_safe_is_15_16`(D-025) · `test_BI_kind_without_safe_grade_injects_fallback`(S-010) · 기존 `ensure_top_safety` 테스트(S-001·S-004 형) | S-001 · S-008 · S-009 · BR-P01(전부 '16' 단독 유지) · D-003 |
| **BH** 🔴 | 추천 질의(골라/추천)에 SQL 이 집계만(COUNT/AVG, GROUP BY 없음)이면 표준 목록 SELECT + `ORDER BY applied_yield DESC LIMIT 5` 로 재작성(`ensure_count_query` 의 역방향 분기 — 같은 함수). 남는 다열 집계 1행은 `_bond_avg_answer` 를 다열로 확장해 기계 조립 | `ensure_count_query` 자리(뒤에 evidence·representative·tie_break·topn 가드가 그대로 붙는다). 충돌: `_COUNT_SKIP_Q`(골라·추천)가 이미 이 질문을 개수 질문에서 제외 — 역방향의 트리거로 재사용 → `test_BH_reco_aggregate_to_list`(D-025 5행 = gold) · `test_BH_multi_agg_row_assembled` · 기존 `test_avg_answer_*` | D-031·D-039·D-040·A-044(개수 질문 — 역방향 미발동) |
| **BG** 🔴 | 정렬 축 어휘 `(높은|낮은)\s*(것|거|걸|채권|종목|편|쪽)` 로 끝나는 목록 요청은 랭킹 — 단 바로 앞에 최상급(가장·제일·젤)이 오면 제외(사실확인 최상급) | `_RECO_Q`·`_RANK_Q` 확장(고정폭 lookbehind). 충돌 🔴: F-021 '수익률이 가장 높은 채권은 뭐야?'·D-030 '제일 높은 채권' 은 C0 728.524% 가 정답 — 랭킹으로 읽으면 고위험제외가 붙어 회귀. `_TOPN_RANK_Q` 는 건드리지 않는다(HCX 가 LIMIT 5 를 이미 냄) → `test_BG_axis_phrase_is_rank`(D-020 1위 롯데캐피탈410-6) · `test_BG_superlative_fact_not_rank`(F-021·D-030 문형) | F-021 · D-030 · D-002 · D-012 · D-033 · D-034 · C-016(BF 가 먼저 되묻는다) |
| **BF** 🔴 | ① `_RISK_CUE` 에서 `국공채|회사채` 를 뺀다(종류 낱말은 위험 축 단서가 아니다) ② '등급' 이 신용/위험/리스크/안전 한정어·등급값(AAA·1등급) 없이 높낮이 어휘와 오면 되묻기(clarify.다의어.등급 강제 부착) — `grade_token_clarify` 에 분기 추가 | `risk_ambiguity_clarify` · `grade_token_clarify`. 충돌: D-003 '위험이 가장 낮은 등급의 채권' 은 '위험' 단서로 불개입(✅ 유지) · test_round25 의 되묻기/불개입 목록 → `test_BF_risky_with_kind_word_clarifies`(X05) · `test_BF_grade_ambiguous_clarifies`(C-016) · `test_BF_grade_with_cue_untouched`(D-003·D-001·U-018·X01) | BR-X03 · BR-X06 · D-003 · D-001 · U-018 · BR-P07 · BR-X01 |
| **BD** 🔴 | 재생성 전에 결정층이 고친다: ① `IN TRIM('x'), TRIM('y')` · `IN (…), TRIM('x'))` → `IN ('x','y')`(꼬리 여분 `)` 함께) ② 따옴표 불균형 LIKE 조각의 OR 가지 제거(AND 절이면 다음 `)` 앞에서 닫기) ③ 스키마 밖 컬럼이 GROUP BY/ORDER BY 항에만 있으면 그 항 제거 | ①② 는 체인 맨 앞(`rewrite_dialect_top` 옆 — 정규화 층) · ③ 은 `drop_unknown_select_columns` 확장(SELECT·GROUP BY·ORDER BY). 충돌: ① 뒤 'AA' 는 값 검사에 걸린다 → `expand_grade_comparison`('AA 이상')·`prune_dead_in_literals` 가 받는지 확인, 안 받으면 재생성으로(BP③ 과 충돌 — BP③ 은 발행사 컬럼 위반에만) → `test_BD_in_trim_literals`(D-037) · `test_BD_trailing_trim_and_paren`(D-045 → 5행 = gold) · `test_BD_unbalanced_like_branch`(D-010) · `test_BD_group_by_unknown_column`(S-004 → SC은행 3종) | D-037 · D-045(재생성 1회 절약) · S-009 |
| **BE** 🔴 | 구조 낱말(`_STRUCT_ALIASES` 키 — 코코본드·조건부자본증권·전환사채·CB·영구채·신종자본증권·후순위…)이 질문에 있고 WHERE 에 그 구조의 판정식이 없으면 `_structure_predicates()[라벨]` 을 AND 주입하고 pd_nm LIKE 조각은 걷어낸다 — 판정식은 선언(구조표시 CASE)에서 읽는다 | `ensure_kind_filter` 에 구조 블록 추가(종류 블록 앞). 충돌: D-009 '영구채'·BR-X11 '신종자본증권' 의 서버 SQL 은 `pd_nm LIKE '%신종%' OR '%영구%'` = 판정식 그대로 → 정규화 포함 판정으로 불개입이어야 한다. `_KIND_NEG_Q` 면 불개입. `fix_structure_kind_literal`(bd_knd 값으로 쓴 라벨)과 역할 분리: 그쪽은 치환, 이쪽은 부재 시 주입 → `test_BE_coco_predicate_injected`(D-010 → 222) · `test_BE_untouched_when_predicate_present`(D-009·X11 SQL) | D-009 · BR-X11 · D-019 |
| **BJ** 🔴 | 안전·위험 최상급 동반(`_TOP_SAFE_Q` ∧ `_TOP_RISK_Q`)이면 두 가지 UNION ALL 템플릿(각 LIMIT 1 · 위험 쪽은 고위험제외 미적용)으로 SQL 을 세우고 `/*TOPBOTH*/` 마커를 남긴다; `_bond_list_answer` 는 이 마커면 UNION 을 허용하고 머리줄을 '가장 안전/가장 위험 각 1종목' 으로 | `ensure_top_safety` 의 `_TOP_RISK_Q` 불개입 분기 → 템플릿. 충돌: `apply_union_branch_guards`(가지별 확정식 — ETF·펀드 전용이라 무해) · `ensure_limit`(가지 안 LIMIT 있음 → 불개입) · `_bond_coverage_counts`(UNION 이면 None → 머리줄 총량 생략) → `test_BJ_both_extremes_template`(S-007 2행 · 6등급 1 · 1등급 C0 1 · '제외했습니다' 없음) | BR-X03(되묻기가 먼저) · S-001 · BR-P01 |
| **BK** 🔴 | '이자를 안 주는/없는·무이자·무이표·제로쿠폰' = `TRIM(bd_intp_tcd)='할인채'` 로만(다른 이자유형 리터럴·bd_inrt_tcd 오용 교체 — `ensure_kind_filter` 의 이자유형 블록) · '왜/이유' 질의는 목록 대신 설명 조립(할인 발행·차액=이자·표면금리 0 은 구조) + 종목 수(커버리지 실측) | 답변 조립기 `_bond_list_answer` 앞 설명 경로. 충돌: `ensure_coupon_type_split` 은 `_INTP_NAMED_Q`(할인채…)면 불개입 — 질문 낱말이 '이자 안 주는' 이라 안 걸림, 하지만 이 가드는 표면금리 랭킹에만 발동해 무관. yaml 규칙 '이유는 스키마에 없다' 를 넘는 서술 금지 → `test_BK_zero_coupon_kind_fixed`(686) · `test_BK_why_answer_explains` | UT-088(주기 부재 기각이 먼저) |
| **BP** 🔴 | ② 재생성 SQL 이 정규화 후 직전과 같으면 trace 에 '#87 형' 마커를 남기고 즉시 종료 ③ 위반이 전부 owner '' 이고 발행사 컬럼(pd_pbcm)이면 재생성 대신 즉시 0건 + 발행사 되묻기 ④ `HCXClient` 가 `last_retries`·`last_wait_s` 를 기록하고 planner 가 노출, pipeline 이 `[Plan] HCX 호출 — 재시도 n회 · 429 대기 s초 · 응답 s초` 를 찍는다 | `answer_question` 재생성 분기 · `hcx/client.py`(기록만) · `hcx/planner.py`. 충돌 🔴: ③ 을 owner '' 전체로 넓히면 D-037 의 'AA'(BD ① 뒤) 같은 등급 오기 위반까지 재생성을 잃는다 — 발행사 컬럼에 한정 → `test_BP_issuer_absent_skips_regen`(U-035 문형) · `test_BP_same_regen_marks` · `test_BP_client_records_retry_stats`(가짜 httpx) | U-035(되묻기 문구 동일) · D-037 |
| **BM** 🟡 | 정렬·집계 없는 채권 목록 SQL 에 mat_dt 조건이 하나도 없고 만기 경과 낱말이 없으면 슬롯 선언문(`query_rules.기본모수.enforce.sql`)을 그대로 AND 주입 — 선언은 손대지 않고 런타임이 읽는다 | `ensure_maturity_lower_bound` 확장(상한만 있을 때 분기 유지). 충돌: `mat_dt = 20260824`(D-038 '오늘 만기')·`< 과거`(D-054·D-055) 는 mat_dt 술어가 있어 불개입. BONDPOP 슬롯이 먼저 발동하면 `mat_dt >=` 가 있어 불개입 → `test_BM_list_without_sort_gets_floor`(D-006 → 385) · `test_BM_untouched_with_mat_predicate` | D-001(이미 하한 있음) · D-009 · D-038 · D-054 · D-055 · BR-X11 |
| **BN** 🟡 | 표면금리 랭킹의 이자유형 절이 확정식(이표채 ∧ 고정금리)과 다르면 그 절을 걷고 확정식으로 교체 | `ensure_coupon_type_split` 불개입 조건 완화. 충돌: `_INTP_NAMED_Q`(사용자가 유형을 콕 집음)는 여전히 불개입 → `test_BN_partial_split_normalized`(D-012 → 14,923) | D-045 · BR-P09(이미 확정식) |
| **BO** 🟡 | (a)~(j) 조립기 고지 묶음 | `_bond_list_answer` · `_zero_count_answer` · `ensure_credit_backstop` · `ensure_reco_sort` — 예산 남을 때만, 항목별 1커밋 | D-032 · S-003 · D-014 · D-026 · D-052 · D-013 · D-011 · S-005 · S-006 · A-015 · S-002 |

## 2. 적용 순서 · 커밋 단위

1. 이 계획(커밋 1).
2. BL → BA → BB(+BI 폴백 주입) → BD → BE → BF → BG → BH+BI → BJ → BK → BP → BM → BN → BO.
3. 커밋마다 동결선 `tests/test_snapshot_round6.py` · 전체 pytest(기준 1,355 passed) · `eval/run_gold_check.py`(195/0) · 87문항 재투입 대조(✅ 51 의 답변·SQL 불변).

## 3. 상태 (2026-09-06 중단 시점)

사용자 이동으로 중단. 코드 편집 0건(계획·재현만). 위 표 0절의 "미착수" 가 전부 다음 세션 몫이다.
