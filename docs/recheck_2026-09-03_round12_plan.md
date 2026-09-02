# 12라운드 수리 간섭 지도 — 2026-09-03

심사관 셋의 §③ 합본 47항(재검 11 · KG 16 · gold 20)에 대한 A 의 구현 계획.
🔴 오케스트레이터 지시: **1순위(가드 상호작용 구조) → 2순위(심사관 실측 확정) → 3순위(회귀·잔여)**.

로컬 재현 완료(구현 전):

```
OFFICIAL-004  IN : … FROM domestic_etfs WHERE cu_base_index LIKE '%Aerospace%' ORDER BY …
              IDX: … WHERE (REPLACE(ref_base_index,' ','') GLOB 'Aerospace' OR … GLOB 'Aerospace[CTP]R*') …
              POP: … WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1 ORDER BY …      ← 조건 전소실 (심사관 실측 재현)
OR 가지 소멸   IN : WHERE cu_base_index LIKE '%우주%' OR pd_nm LIKE '%항공%'
              IDX: WHERE (REPLACE(ref_base_index,' ','') GLOB '항공' OR …)      ← pd_nm 가지 소멸
운용사 축      ref_fund_mgmt_co='Samsung Asset Management Co Ltd' ∧ ETF ∧ 판매중 = 240
              LIKE '%Samsung%' 분포 = Samsung Asset Management Co Ltd 243 · Samsung Active Asset Management 25
              → 265 는 별개 법인 합산. **심사관이 옳다. 접두 LIKE 폐기.**
Ground 실측    '삼성자산운용' → Org_00040010 → cu_fund_mgmt_co='삼성' · ref_fund_mgmt_co='Samsung…' · cu_fund_mgmt_co='삼성KODEX'
              ← 한 줄에 오염·정본 슬롯을 나란히 실어 HCX 가 섞는다(AA21 뿌리)
축 실측        COUNT(DISTINCT 펀드키)=3,040 · COUNT(DISTINCT rptt)=1,919 · R7 두 축 동일(심사관 반증 확인)
```

---

## 1순위 — 가드 상호작용을 구조로 닫는다

| # | (a) 부류 → 일반 규칙 | (b) 닿는 층 / 충돌 지점 → 회귀 테스트 이름 | (c) 경로가 바뀔 수 있는 기존 ✅ |
| :-- | :-- | :-- | :-- |
| **P1** | **부류 Z — 가드가 주입한 술어는 「날조 술어 제거」의 대상이 아니다.** 확정식이 만든 절에 표식(`/*g*/`)을 달고, 날조 판별은 표식 없는 절(=HCX 원문)에만 건다 | SQL 가드 `ensure_etf_index_canon` → `ensure_etf_base_population`. 충돌: 표식이 뒤 가드의 절 분해(`split_conjuncts`·`_flat_conjuncts`)·스키마 검사·실행을 깨면 안 된다 → `test_round12_repairs.py::test_guard_mark_survives_removal` | 표식은 SQL 주석이라 실행 의미 0. AA22(S&P500 24)·X7(KOSPI200 34)은 리터럴이 질문에 있어 이미 살아남던 경로 — 불변이어야 한다 |
| **P2** | **부류 Z 안전망 — 술어 제거가 사용자 조건을 0개로 만들면 제거 자체를 취소한다.** 지우기만 하고 대체를 못 넣는 상태를 만들지 않는다. 원 술어가 남으면 0행 경로로 정직하게 간다(전수 조회보다 낫다) | SQL 가드 `ensure_etf_base_population` 제거 루프 말미의 불변식 → `test_round12_repairs.py::test_removal_never_empties_conditions` | 제거가 **일부만** 걷어내던 문항(U8 `cu_charge_rt>0`)은 남는 조건이 있어 불변 |
| **P3** | **확정식 치환은 술어 단위가 아니라 비교식 단위로.** OR 가지 중 지수 컬럼을 쓴 가지만 canon 으로 바꾸고 나머지 가지는 보존한다 | SQL 가드 `ensure_etf_index_canon`. 충돌: `_flat_conjuncts` 는 최상위 AND 만 나눈다 → OR 가지 분해를 추가 → `test_round12_repairs.py::test_index_canon_keeps_or_branch` | 단일 절 경로(X7·AA22·Z19)는 OR 가지가 1개라 종전과 동일 |
| **P4** | **부류 V — 확정식은 자기가 주입할 컬럼이 그 FROM 테이블에 있는지 먼저 확인한다.** 문장이 다른 테이블을 섞거나(UNION·JOIN·public_funds) ETF 테이블 단독이 아니면 ETF 확정식은 불개입 | SQL 가드 `ensure_etf_index_canon`·`ensure_etf_base_population`. 충돌: 불개입이 늘어 X7·AA22 가 꺼지면 안 된다(그 둘은 domestic_etfs 단독) → `test_round12_repairs.py::test_etf_canon_scope_guard` | X8(자가 오거절)·X15(실행 오류). 단독 ETF 문장은 전부 불변 |

---

## 2순위 — 심사관이 실측으로 확정한 것

| # | (a) 부류 → 일반 규칙 | (b) 닿는 층 / 충돌 지점 → 회귀 테스트 이름 | (c) 경로가 바뀔 수 있는 기존 ✅ |
| :-- | :-- | :-- | :-- |
| **P5** | **부류 AB — 랭킹·묶기 가드가 주입·교체하는 GROUP BY 축을 `_FUND_GROUP_EXPR`(rptt 폴백)로.** 분포·운용사 집계의 `COUNT(DISTINCT _FUND_KEY_EXPR)` 는 손대지 않는다(3,040 유지) | SQL 가드 `ensure_fund_rank_representative` + 조립기 `_fund_rank_answer`·`_list_answer` 의 발동 리터럴. 🔴 **A 의 10R 보류를 심사관 둘이 반증** → `test_round12_repairs.py::test_rank_axis_is_rptt` | S1·V16·Y1 5위 교체(심사관 §③-4 승인 값 변경) · S2·Y3·Y4·Y5·R7 값 불변·클래스수만 참값. R1·T1·V5·R2·Y6 은 펀드 단위 GROUP BY 를 안 쓰므로 불개입(실측 확인) |
| **P6** | **부류 T-2 — ETF 운용사 축 정본화.** ⓐ Ground 는 한 노드에 `ref_*` 정본 슬롯이 있으면 같은 테이블의 `cu_*` 오염 슬롯을 싣지 않는다 ⓑ SQL 가드가 `cu_fund_mgmt_co` 술어를 DB 역조회 최빈 `ref_fund_mgmt_co` 등호로 교체한다. 🔴 **접두 LIKE 금지 — 정식명 등호**(`Samsung Active` 25행은 별개 법인) | Ground `target_aliases`/`_mapping_block` + 새 SQL 가드 `ensure_etf_mgmt_canon`. 충돌: 역조회가 매핑을 못 내면 **아무것도 지우지 않는다**(P2 와 같은 원자성) → `test_round12_repairs.py::test_etf_mgmt_canon_240` | AA21·Z14·KG-025 ETF축·X9 ETF축. 펀드(`public_funds`) 운용사 축은 `or_co_xtn_itt_cd` 라 불개입 |

---

## 3순위 — 회귀·잔여

| # | (a) 부류 → 일반 규칙 | (b) 닿는 층 → 회귀 테스트 이름 | (c) 경로가 바뀔 수 있는 기존 ✅ |
| :-- | :-- | :-- | :-- |
| **P7** | **부류 W — 클래스 축 집계는 SUM 이 아니라 MAX/MIN.** 정렬 축이 클래스 속성(수익률 8종·보수 4종)이면 그 축을 감싼 `SUM`·`AVG`·`TOTAL` 을 방향에 맞는 `MAX`/`MIN` 으로 교체한다. 순자산만 SUM 허용 | `_wrap_sort_col`·`_wrap_order_by_col` → `test_round12_repairs.py::test_class_axis_sum_replaced` | FND-005(gold 5건 일치 실측). 순자산 SUM 경로(U13·Y2) 불변 |
| **P8** | **부류 Z′ — 플래너 전처리가 SQL 을 훼손하지 않는다.** 절단 후 괄호 균형이 깨지면 절단을 취소한다 | `src/hcx/planner.py:extract_sql` → `tests/test_planner.py::test_extract_sql_keeps_union_paren` | CROSS-003 및 UNION 교차질의 전부. 잡담 절단이 정상인 경로는 균형이 안 깨져 불변 |
| **P9** | **부류 AA — 조립 발동 판정에서 식별 컬럼도 잡음이다.** `_lookup_answer` 의 `class_only` 잡음 집합에 `_FUND_ID_COLS` 를 넣는다 | 조립기 `_lookup_answer` → `test_round12_repairs.py::test_lookup_class_only_ignores_id_cols` | V12 회귀 회수. W5·T6·U16 감시 |
| **P10** | **부류 V′ — 랭킹 GROUP BY 축 판정에서 기본모수 컬럼을 뺀다.** `sale_yn`·`prvo_pbff_desc` 는 전 행 동일값이라 축으로서 정보가 0 | `ensure_fund_rank_representative` 축 판정 → `test_round12_repairs.py::test_rank_axis_ignores_base_population_cols` | U14. T1·V5·R2·Y6 은 운용사 확정식이 먼저 도는 순서를 유지해 불개입 |
| **P11** | **부류 Z 잔존 — 억원 병기도 「불일치 시 교체」.** 표시 열의 분모·단위가 확정식과 다르면 교체하고, 절사(`CAST(x/1e8)`)를 `ROUND` 로 통일한다 | `ensure_amount_eok_columns` → `test_round12_repairs.py::test_eok_display_replaced_on_mismatch` | T3 331,098 vs T2·V5 331,097 — ±1억 이동. 🔴 **동결선 확인 필수**(값 계열) |
| **P12** | **부류 Y — 결과 전사는 스키마 한글명으로.** `ensure_rows_answered` 가 SQL 헤더 원문 대신 `_fund_col_ko` 라벨을 쓰고 식별자·내부코드 컬럼은 뺀다 | 조립기 `ensure_rows_answered` → `test_round12_repairs.py::test_rows_answered_uses_ko_labels` | OFFICIAL-005·FND-R03 |
| **P13** | **금지 문형은 어휘가 아니라 문형으로.** 면책 사전에 `권장/권고합니다`·`참고용으로만`·`유용한 정보를 제공` 계열 유보·권유 문형을 더한다 | `strip_disclaimer` 의 `_DISCLAIMER` → `test_round12_repairs.py::test_disclaimer_covers_recommend_form` | U9·X13 꼬리·OFFICIAL-003. 데이터 유래 주의 문구(수익률 누적 고지)는 조립기가 굽는 것이라 대상 아님 |

---

## 추가 구현 (계획 뒤 착수)

| # | (a) 부류 → 일반 규칙 | (b) 닿는 층 → 회귀 테스트 | (c) 결과 |
| :-- | :-- | :-- | :-- |
| **P14** | **부류 D·G — 개체 개수 랭킹의 정렬 축은 `COUNT(DISTINCT 펀드키)`.** 펀드수·클래스수를 구분 병기하고 `COUNT(*)` 를 '펀드 N개' 로 옮기지 않는다 | 새 가드 `ensure_fund_entity_count_ranking` → `test_entity_count_ranking_axis` | KG-008 → gold 714·516·465 |
| **P15** | **부류 M·U — KG 미매핑 운용사는 코드를 지어내기 전에 DB 역조회로 확정.** 법인 접미를 뗀 브랜드 어간 대조(하드코딩 0) + 확정된 토큰의 잔여를 상품 고유명으로 재해석하지 않는다 | Ground `mgmt_code_from_question`·`residual_name_token` → `test_mgmt_code_reverse_lookup` · `test_residual_token_skips_corporate_suffix` | Z15·AA23 → 00040013 15/46 · X12 거짓 0 소멸 |

## 🔴 보류(구현하지 않음) — 사유 명시

- **KG ③-6 보완규칙 · ③-11 · ③-14 · ③-15 · gold ③-13~③-19** 등 조립기 서술 계열 다수 — 예산 배분상 1·2순위 구조 수리를 완결하는 쪽을 택했다. 값 결함이 아니라 서술 결함([B] 등급)이다.
- **gold ③-16 clarify 경로** — 게이트 신설이 필요하고 감점 축(UNANS·OFFICIAL-NA 9건 전부 동일 바이트)을 흔들 위험이 커서 이번 라운드 제외.
- **KG ③-13 운용사 코드 역조회(Z15·AA23·X12)** — Ground 신설 필요. P6 과 같은 층이라 다음 라운드에 P6 확장으로 붙이는 것이 안전하다.
- **재검 ③-7 목록 접기 · ③-11 정본 축** — 심사관 스스로 "축을 정하지 않으면 표시 문구로만 덮을 수 있다"고 적었고 리드 판단 대기 항목이다.
- **gold ③-F FND-008 비결정성** — `ontology/enums/public_funds.yaml` 변경 요구. 🔴 경계상 **구현하지 않고 보고**한다.
- **gold ③-9** 「전사 강제는 `answer_rules` 명시 기각을 덮지 않는다」 — 조립기가 기각의 출처(규칙 기각 vs 결과를
  보고도 못 봤다는 거절)를 구분할 신호를 아직 받지 않는다. 신호 배선이 선행돼야 한다.
- **KG ③-9(AA16 절반)** — 기본모수 존재 판정을 WHERE 절로 좁히면 AA16 이 닫히지만, **개별 조회 경로가 같은
  전체-SQL 판정에 의존한다**(묶기 가드가 SELECT 에 싣는 `판매중클래스수` CASE 를 모수 언급으로 읽어 '판매중'
  주입을 막고 있고, 그 경로는 판매완료 14,707행을 0행 오거절 없이 조회해야 한다). 좁히면 동결선 S5·W5·X18 의
  `where` 가 바뀐다 — **실측으로 확인하고 되돌렸다.** 별도 판단 사안.
- **X12 역외 형제 합산** — gold 28/59 = 국내 15/46 + 역외 `00130003` 13. 역외 법인 합산은 `_offshore_sibling_note`
  계열의 별도 처방이라 이번 라운드 제외.

## 동결선

항목마다 `tests/test_snapshot_round6.py` → 전체 pytest → `eval/run_gold_check.py` 순으로 확인한다.
P5·P11 은 값이 움직이는 항목이라 동결선이 깨지면 **되돌리고 보고**한다(심사관 명시 승인분은 근거를 커밋 본문에 인용하고 갱신).
