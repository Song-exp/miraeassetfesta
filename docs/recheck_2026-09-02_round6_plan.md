# 6라운드 수리 계획 — 간섭 지도 먼저 (에이전트 A · 2026-09-02)

> 지시서: `docs/recheck_2026-09-02_round5.md` §③ (N·O·P·I′·J′) + `docs/kg_structure_probe_round3_2026-09-02.md` §③ (F1~F6).
> 원칙: 구현 전에 각 항목이 **닿는 기존 규칙·가드·KG 층**과 충돌 지점을 적고, 그 지점을 고정할 회귀 테스트를 이름으로 못 박는다.
> 고정선: 5R 재검 ✅(값 ✅ 포함) + KG 2R/3R ✅ 문항의 결정층 결과(라우팅 테이블·Ground 노드·가드 후 SQL WHERE·조립기 마커)를
> `tests/test_snapshot_round6.py` 가 `tests/snapshots/round6_fixedline.json` 과 대조한다(HCX 0회 — r5 원본의 최종 SQL 을 가짜 플래너로 재투입).
> 어떤 항목이 이 고정선을 깨면 그 항목은 구현하지 않고 보고한다.

기존 규칙 약칭: **I** Country 독립 낱말(4R) · **N4** token canon 전 축 · **S4** Region closure scope · **S1** 라벨 슬롯 · **PC** `_sql_precheck` ·
**RT** 오타 라우터('펌드'·'투자신탁') · **MT** 운용사 템플릿(Q2-a/P) · **M** 개별 조회 묶기 · **R10** '유형'→zrin_ptn_nm · **K** Ground 0 고유명 후보 ·
**J** 코드 핀 생략 분기 토큰 · **B-4** 억원 병기.

| # | (a) 부류 → 일반 규칙 | (b) 간섭 지도 — 닿는 층 / 충돌 가능 지점 → 고정 테스트 | (c) 경로가 바뀔 수 있는 ✅ 문항 |
| :-- | :-- | :-- | :-- |
| **N** 🔴 | Ground 0 고유명 후보 → 일반어 제거 사전에 PRODUCT 키(오타 '펌드'·'투자신탁' 포함)를 넣고 잔여 <2자면 후보 없음 | **RT↔K**: 라우터가 소비한 머리명사가 K 후보로 승격(R7·S1). 같은 사전(PRODUCT)을 K 가 보게 함. 위험: '투자신탁' 이 PRODUCT 키라 '삼성코리아대표증권자투자신탁' 의 잔여가 '삼성코리아대표증권자' 로 줄어듦 → 규칙: 낱말 **안**에 명사가 든 경우는 낱말 전체 유지(제거는 낱말 전체가 일반어+명사로만 이뤄질 때만). → `test_r6_N_standalone_token_product_keys` · 기존 `test_r4_skip_pin_token_J_K_L` | T7(투자신탁 정식명 후보) · W5·W8(호수 질의 K 경로) · S12(코어테크 펌드) |
| **O** 🟠 | 0행 결정 → 단독 0건 절이 숫자 리터럴 비교이고 그 숫자가 질문에 없으면 절 제거 후 1회 재실행 | **PC/기점오류 가드**: 재실행 SQL 도 같은 체인 산출물(가드 재적용 없음 — 절만 제거). **G-1 이월**과 자리 겹침 없음(랭킹 템플릿 전엔 O 가 담당). 위험: 사용자 숫자(등급 '2', 연도)는 질문 텍스트에 있으므로 제외 규칙으로 보호 → `test_r6_O_numeric_clause_rerun` · 기존 `test_fund_rank_group_by_injected`(MIN 경로) | S2 · KG-014(등급 0 — 게이트가 먼저) · 만기·연도 질의(채권 — 숫자가 질문에 있어 불개입) |
| **P** 🟠 | MT 부가 절 = 단순 술어만 · PC 에 WHERE 내 `OVER(`/집계 기각 · 실행 실패 → 재생성 1회 | **MT↔HCX 잔재**: extra 필터가 `OVER(` 절을 보존(V5). **PC**: WHERE 안 집계 검사가 채권/ETF `HAVING` 정상 SQL 을 기각하지 않게 WHERE 절 범위만 → `test_r6_P_template_simple_predicates` · 기존 `test_fund_manager_ranking_template`(부가 조건 보존) | S11·T1·T2·R2·V5 |
| **I′** 🔴 | Country 경계·성분 판정을 원문 question 기준 · 라벨을 **포함하는 낱말 전체**를 DB 덩어리로 · 이름 토큰이 실리는 개별 조회엔 Country 태그 불탑재 | **I↔R10**: KG-012 '중국주식 유형' 은 성분 판정을 건너뛰어야 함(유형 분기 유지). **I↔S4/Region**: Region 노드는 대상 아님. **I↔J**: 성분이면 낱말 전체가 토큰(브랜드 포함 — Q 이월과 같은 결) → 기존 Org 잔여 토큰('베트남그로스')과 충돌 시 **낱말 전체 우선**. **M**: 태그 불탑재는 이름 토큰 존재 시 `ensure_fund_country_tag` 불개입 → `test_r6_Iprime_word_component_and_no_tag` · 기존 `test_r4_country_name_component_I`·`test_country_attr_tags_from_kg` | T14·V15·S4·W4·W7·W12·T4·T13·KG-019/020/021 |
| **J′** 🔴 | 가드 체인 끝 사후조건: 토큰이 있는데 LIKE 리터럴 어느 것도 토큰을 품지 않으면 `ensure_fund_name_filter` 재실행 | **호수 가드↔이름 필터**: 'N호' 절 제거가 이름 LIKE 를 삼킴(W6). 사후조건은 멱등(N2 치환 규칙 재사용). **M**: `_has_name_filter` 참 → 묶기 → `_list_answer` 로 빠지지 않음 → `test_r6_Jprime_postcondition_name_like` · 기존 `test_r4_skip_pin_token_J_K_L`(T6) | T6·R6·W5·T9·S5 |
| **F1** 🔴 | FundAttribute 라벨이 Region·AssetClass·Country 라벨·상품군 명사·'국내/해외/글로벌' 과 같으면 매칭 키·`_attr_word_map` 제외(alias 로만) — 충돌 목록은 빌더 V-검증이 계산해 kg_coverage_report 에 남김 | **N4↔S4/Region**: 'ETF'(M113)·'중국'(W-축)·'국내'(V101) 라벨이 Region/상품군 명사를 가로챔(KG-023·025·026·X8·X9·X15·X16). 런타임은 kg_node.provenance='label_conflict' 로 읽음(빌더 산출). **R10/N4 정상 경로**(반도체·폐쇄형)는 충돌 없음 → `test_r6_F1_label_conflict_excluded` · 기존 `test_attr_tag_all_axes_N4`·`test_country_attr_tags_from_kg` | KG-024(반도체 유지) · KG-017/018 · R3·S6·S7·T4·T5·T13·W12 (국가 목록 — Region 매핑 복귀) |
| **F2** 🔴 | 개별 조회 묶기: 클래스 종속 값(기준가·수익률·보수·설정일)은 MIN~MAX 범위, 클래스 공통(순자산 합·등급·수탁)은 대표값 — 단일 MAX 로 대표명에 붙이지 않음 | **M/조립기 `_lookup_answer`**: 새 `_최고/_최저` 컬럼이 늘어나면 조립기가 '기준가 X원~Y원' 문형을 알아야 함(수익률 8종 외 enums 컬럼 메타로 종속 여부 판정). **B-4**: 기준가는 원 단위지만 금액 아님(억원 병기 안 함) → `test_r6_F2_class_dependent_range` · 기존 `test_fund_lookup_grouping`·`test_lookup_answer_assembled` | R4·S3·T14·W2·W3·W9·V1·V4·T8·T12 (열 순서 불변 — 끝에 추가) |
| **F3** 🟠 | 구성종목·설명서 질의: `ext_fund_holdings`(grp+or_co)/`ext_fund_page`(estb_dt) JOIN 템플릿 기계 주입 + PC 테이블 범위 검사를 컬럼 검사 **앞**으로 | **N1(PC 순서)**: 순서만 바뀜 — 메시지가 "테이블이 틀렸다" 로. **ensure_ext_join(Q1-c)**: 1:1 ext 만 자동 주입했던 규칙과 겹침 → holdings 는 질문 트리거('보유/담은/구성종목')가 있을 때만(팬아웃 허용 = 질의 의도) 같은 함수 확장. **M**: 보유종목 결과는 묶기 대상 아님(`_has_name_filter` 이지만 JOIN → 불개입) → `test_r6_F3_holdings_join_template` · 기존 `test_ext_join_injected`·`test_kg2r_table_scope_and_name_pin_N1_N2_M` | KG-028·X1·X2·KG-034·X4(설정일)·T9 |
| **F4** 🔴 | 0행 문구 세 갈래 (a)교집합 0 (b)기본모수 0·이름 폴백 (c)식별 실패 — LIKE 리터럴도 값사전 대조 · `_count_answer` 0 문구 동일 | **R1(교집합 0 문구)** 를 세 갈래로 대체. **I↔R10 구멍**: `ensure_fund_country_tag` ⓐ 가 등호만 치환하고 `fd_ivst_rgn_desc LIKE '%중국%'` 통과(KG-012) → 확정식 ⓐ 에 LIKE 포함. **N2**: 이름 오타는 N2 가 먼저 토큰으로 치환하므로 (c) 는 Ground 0 오타('코어택')만 → `test_r6_F4_zero_row_three_ways` · 기존 `test_count_answer_subject_all_roles`(KG-011 교집합 0) | KG-011·KG-014·S8·S9·R5·T11(0 아님 — 문구 불변) |
| **F5** 🟡 | 교차 집계 분기별 SQL·모수·기계 합산, 미조회 분기 '미조회' | **MT·N1·F1** 뒤에서만 의미 있음 — 예산 남을 때만 | X8·X9·X15·KG-025/026 |
| **F6** 🟠 | 기본모수 판정 = `sale_yn = '판매중'` **단독 절**(OR/IS NULL 은 교체) · 펀드단위 COUNT 치환을 LEFT JOIN/서브쿼리 경로에도(`p.` 한정) | **기본모수 가드↔N2/템플릿**: 이미 `sale_yn` 이 있으면 존중하던 규칙 변경 → 교체 시 `_POP_WIDEN` 존중 유지. **R7↔Q1-b(JOIN 한정)**: 펀드단위 키 식이 JOIN 에서 `itm_no` 비한정 → 한정자 붙여 생성 → `test_r6_F6_base_population_strict_and_join_count` · 기존 `test_fund_base_population_injected`·`test_fund_distinct_count_replaced` | R5·S8·S9·T11·KG-001/004(개수 조립 불변) · X19·KG-035·KG-005·X10 |

## 적용 순서 · 커밋 단위
1. 고정선 스냅샷(`tests/test_snapshot_round6.py` + json) — 이 계획과 같은 커밋 다음.
2. N → F1(빌더 변경 · KG 재빌드) → F2 → I′+J′(한 커밋) → F4 → O → P → F3 → F6 → (F5 예산 시).
3. 항목마다 (b) 의 회귀 테스트 + 스냅샷 통과 → 커밋. 스냅샷을 깨면 구현하지 않고 보고.
