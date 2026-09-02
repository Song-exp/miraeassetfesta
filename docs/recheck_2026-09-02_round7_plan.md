# 7R 수리 간섭 지도 — 재검 §③(M′·R′·S′·P′·B-4′) + KG §③(G1~G7·F3)

두 심사관 §③ 13항을 합쳐 처리한다. **항목 13개를 각자 때우지 않는다** — 6R 실측 SQL 을
전부 대조한 결과 13항이 **뿌리 7개**로 접힌다. 접는 근거를 아래 §0 에 적고, 뿌리 단위로 커밋한다.

원본 대조 자료: `eval/probe_recheck_2026-09-02_r6.json` · `eval/probe_recheck_2026-09-02_r6_kg.json`
(최종 SQL 을 문항별로 뽑아 확인 — 아래 인용 SQL 은 전부 그 파일의 실측이다).

---

## §0 뿌리 접기 — 왜 13항이 7뿌리인가

### 뿌리 ① 「가드 발동이 HCX 의 SQL **모양**에 달렸다」 = M′ + R′ + G1 + F6′ (7문항)

같은 문장 하나로 다 설명된다: **가드의 발동/불개입 조건이 HCX 가 낸 SQL 의 형태
(정렬 유무·집계 함수·GROUP BY 축)를 읽는다.** HCX 가 모양을 바꾸면 가드가 통째로 비켜간다.

| 문항 | 실측 SQL 의 어느 모양이 가드를 비켰나 | 가드 |
| :-- | :-- | :-- |
| S4 | `ORDER BY itm_no ASC` | `ensure_fund_lookup_grouping` 조건 ③ |
| T14 | `AVG(fd_nast_suma)` | 〃 조건 ④ |
| V12·W5 | `GROUP BY itm_no` + 질문에 '클래스' | 〃 조건 ①·⑤ |
| KG-018 | HCX 원 SQL 에 ORDER BY·집계 **없음** → 기본모수 가드 조건 ② 미달 → 그 **뒤에** 목록 묶기가 ORDER BY·COUNT 를 붙였다 | `ensure_fund_base_population` |
| W2·Y11 | 〃 (개별 조회 원 SQL 이 정렬·집계 없음 → 묶기가 나중에 붙임) | 〃 |

→ **하나의 처방**: 발동 조건에서 「모양」을 뺀다. 묶기는 `JOIN`·`UNION`·펀드키 아닌 진짜
GROUP BY 만 불개입 사유로 남기고, 기본모수는 **체인 끝에서 한 번 더** 돈다(멱등).
6R F6′ 이월표가 요구한 「개별 조회엔 `공모`만」은 그 재호출의 인자로 처리한다 —
KG §③ G1 의 「전 SELECT 에 양쪽 다」와 충돌하는 지점이라 **아래 §1 에 간섭 항목으로 따로 적었다.**

### 뿌리 ② 「핀·값이 엉뚱한 컬럼에 실려도 통과」 = S′ 앞부분 (W11)

`itm_no IN ('030230002D36')` — 이 값은 `rptt_ksd_itm_no` 에만 있다. `check_code_literals` 는
`*_itt_cd` 만 본다. 펀드 키 3종(`itm_no`·`rptt_ksd_itm_no`·`mtco_itm_no`)이 검사 밖.
Ground 를 참조할 필요가 없다 — **DB 실측만으로** "이 컬럼엔 0행, 형제 키 컬럼엔 있다" 가 판정된다.

### 뿌리 ③ 「사용자에게 SQL·코드가 날것으로 나간다」 = S′ 뒷부분 + G4 + B-5 + 면책 범위

세 문항이 같은 층(답변 표면)에서 같은 실패를 한다 — **기계가 확정하지 못한 자리를 원문/HCX 가 메운다.**

| 문항 | 실측 | 자리 |
| :-- | :-- | :-- |
| W11 | 0행 문구에 `itm_no IN ('030230002D36')` 절 원문 | `_zero_row_reason` 마지막 갈래 `lit or desc or c.strip()` |
| KG-008 | `trim(trusc_xtn_itt_cd) as 수탁회사명` → HCX 가 **운용사 이름을 날조** | `_hide_answer_columns` 가 별칭만 보고 코드 컬럼을 못 알아봄 |
| Y16 | "긍정적으로 검토해볼 수 있을 것" 투자권유 | `_DISCLAIMER` 사전이 '기관 문의' 계열만 덮음 |
| Z21·Z23 | 부재·유보 경로엔 면책 필터가 안 걸림 | `strip_disclaimer` 호출 지점이 성공 경로 1곳 |

### 뿌리 ④ 「숨김과 병기가 짝이 아니다」 = B-4′ (Y16 값 소실)

`ensure_amount_eok_columns` 는 `public_funds|domestic_etfs` 만, `_hide_answer_columns` 는 전 테이블.
`overseas_etfs.du_last_aum` 이 대체 열 없이 삭제 → 숫자 0개 → 환각·투자권유가 빈칸을 메웠다.
뿌리 ③ 과 **같은 함수(`_hide_answer_columns`)를 고치고 같은 문항(Y16)을 닫으므로 한 커밋**으로 간다.

### 뿌리 ⑤ 「precheck 가 문법을 안 본다」 = G6 (Z13)

`[Guard] SQL 검사 통과` → `OperationalError: near ")"`. 괄호 불균형이 실행까지 갔다.
`sqlite3.complete_statement` + `EXPLAIN` 드라이런 두 줄.

### 뿌리 ⑥ 「질문이 정한 축이 SQL 에서 소실된다」 = P′ + G3

Y7 실측 최종 SQL 의 WHERE 는 `p.sale_yn AND p.prvo_pbff_desc` 뿐 — `주식형` 이 없다.
Z10 은 `zrin_btyp_nm = '인도주식형'`(사전 밖 값), Z5 는 `fd_ivst_rgn_desc IN ('글로벌','해외주식형')`.
전부 **"질문이 고른 축의 값이 SQL 에 정확히 실려 있는가"** 한 물음이다.
`ensure_fund_attr_tag`/`ensure_fund_country_tag` 가 이미 「치환」을 하고 있으므로
**같은 함수에 「없으면 주입」을 더한다** (새 가드 만들지 않음 — 중복 0 원칙).

### 뿌리 ⑦ 「날짜·클래스표기 축 확정식」 = G2 + G7 · 「구성종목 템플릿」 = F3 · 「조립 사후 대조」 = G5

셋은 서로 독립이고 각자 새 규칙이 필요하다. 예산 하위 순위.

---

## §1 간섭 지도 (a)부류→일반규칙 / (b)닿는 층·회귀 테스트 이름 / (c)경로가 바뀔 수 있는 ✅ 문항

| # | (a) 부류 → 일반 규칙 | (b) 닿는 층 / 충돌 지점 → 회귀 테스트 이름 | (c) 경로가 바뀔 수 있는 기존 ✅ |
| :-- | :-- | :-- | :-- |
| **뿌리①-A** M′+R′ | 개별 조회(이름 LIKE 또는 펀드키 핀)로 판정되면 HCX 의 `ORDER BY`·SELECT 집계·`GROUP BY itm_no` 는 불개입 사유가 아니다. 불개입은 `JOIN`·`UNION`·**펀드키 아닌** GROUP BY 일 때만. `_LOOKUP_ROW_UNIT` 은 **값이 클래스마다 갈리는 질의(보수·수수료)** 로 좁힌다 — '클래스 개수/열거' 는 펀드키 묶기가 정답 | SQL 가드 `ensure_fund_lookup_grouping` + 조립기 `_lookup_answer`. **충돌**: `ensure_fund_rank_representative`(ORDER BY 랭킹)·`ensure_fund_list_grouping`(목록) 과 같은 SQL 을 두고 다툰다 — 이름 필터가 있어야만 개입하므로 목록 경로와는 안 겹치지만, 랭킹 경로(이름+ORDER BY 수익률)는 겹칠 수 있다 → `test_lookup_grouping_shape_invariant` | T6·R6·S5(현재 비결정 통과) · V13 · W3·W7·Y8~Y15 · X25·Z2·Z3 |
| **뿌리①-B** G1+F6′ | 기본모수 주입은 SQL 모양과 무관하다 — 가드 체인 **끝**에서 한 번 더 돈다(멱등). 개별 조회 경로는 `prvo_pbff_desc='공모'` 만(판매완료 개별 조회 0행 오거절 방지 — `판매중클래스수` 병기는 현행 유지), 그 밖은 양쪽 다 | SQL 가드 `ensure_fund_base_population` 재호출. **🔴 두 심사관 충돌**: KG §③ G1 은 "전 SELECT 에 `sale_yn` + `prvo_pbff_desc`", 재검 §③ F6′ 는 "개별 조회엔 `공모`만". 실측 근거가 갈라진다(G1 근거 KG-018·Z18 은 집계·목록 / F6′ 근거 W2·Y11 은 개별 조회) → **질의 부류로 분기**해 둘 다 만족시킨다 → `test_base_population_post_chain` | W2·Y11·KG-018 은 값이 바뀐다(의도) · **X4·X6·KG-002·KG-031 등 모수 머리줄이 있는 ✅ 전부**가 후보 → 동결선이 1차 판정자 |
| **뿌리②** S′ 앞 | 펀드 키 컬럼(`itm_no`·`rptt_ksd_itm_no`·`mtco_itm_no`)의 등호·IN 리터럴이 그 컬럼에 0행이고 **형제 키 컬럼 정확히 하나**에 실재하면 컬럼을 그쪽으로 교정한다(DB 실측 1회). 어디에도 없으면 종전대로 값 검사에 맡긴다 | SQL 가드(새 함수 `ensure_fund_key_column`, `_apply_sql_guards` 안). **충돌**: `ensure_fund_series_boundary`·`ensure_fund_name_filter` 가 만든 절과 겹치지 않음(그들은 `itm_nm`) → `test_fund_key_column_correction` | V4(5R SQL 은 이미 `rptt_ksd_itm_no` — 불변이어야 한다) |
| **뿌리③+④** S′ 뒤 · G4 · B-4′ · B-5 | ① 답변 표에 코드 컬럼 값이 **이름 매핑 없이** 실리지 않는다 — 판정은 **별칭이 아니라 원 컬럼 표현식**, 매핑은 `kg_node.label_official`, 없으면 `코드 X(기관명 미수록)` 로 기계 표기(숨기지 않는다 — 숨김이 '부재' 서술을 낳았다) ② 금액 원값은 **대체 표시 열이 실제로 있을 때만** 숨긴다 ③ 0행 문구는 어떤 갈래에서도 SQL 절 원문을 노출하지 않는다(리터럴 추출을 `=`·`LIKE`·`IN` 으로 넓히고, 못 뽑으면 (a) 갈래) ④ 금지 문형 사전에 투자권유형을 넣고, **부재·거절 경로에도** 같은 필터를 건다 | 조립기 `_hide_answer_columns`·`_zero_row_reason`·`strip_disclaimer` 호출 지점. **충돌**: `_HIDE_FROM_ANSWER`(prfd_attr_cds)는 종전대로 숨김 유지 — 그건 명칭 열(`zrin_attr_nms`)이 병기되는 대체 열 있는 경우다 → `test_answer_surface_rules` | R3(prfd_attr_cds 숨김) · V7·W10(억원 열 있어 원값 숨김 유지) · Z21·Z23 |
| **뿌리⑤** G6 | SQL 은 실행 전에 파싱된다 — `complete_statement` + `EXPLAIN` 드라이런. 실패는 재생성 피드백으로 | 가드 `_sql_precheck`. **충돌**: `validate_sql` 의 단일문 검사와 목적이 겹친다 → 새 함수 만들지 말고 **`validate_sql` 안**에 넣는다 → `test_precheck_parses_sql` | 전 문항(통과 SQL 은 EXPLAIN 도 통과 — 무해해야 한다) |
| **뿌리⑥** P′+G3 | 질문이 고른 축의 값이 SQL 에 실려 있어야 한다 — 확정식 가드는 「찾아 바꾸기」에 더해 **후보 절이 하나도 없으면 AND 주입**한다. 운용사 확정식은 단순 술어 부가 절을 전부 보존한다 | 가드 `ensure_fund_attr_tag`/`ensure_fund_country_tag` + 템플릿 `ensure_fund_manager_ranking`. **충돌**: 확정식 주입이 `ensure_fund_manager_ranking` **뒤**에 돌아야 템플릿이 지운 축이 되살아난다(현 체인 순서상 mgr 가 먼저) → `test_axis_clause_preserved` | Z10·Z5·Z11·Z25·KG-012·KG-024 |
| **뿌리⑦** G2·G7·G5·F3 | 예산 하위. 손대면 각자 새 확정식이 필요하고 (c) 후보가 넓다 | — | — |

### 예측하는 회귀 (b) 의 요약

1. **뿌리① 과 뿌리⑥ 의 교집합** — 개별 조회 묶기가 넓어지면 축 확정식이 만든 `zrin_ptn_nm` 절을 가진
   SQL 도 묶기 대상이 된다. 과거 회귀(Country 노드 ↔ 상품명 안 국가어)와 같은 형태.
2. **뿌리①-B 와 동결선** — 체인 끝 기본모수 재주입은 ✅ 문항의 WHERE 를 넓게 바꾼다. 동결선이
   깨지면 되돌린다(지시서 제약).
3. **뿌리③ 과 R3** — 코드 컬럼을 '숨김' 에서 '표기' 로 바꾸면 R3 의 `prfd_attr_cds` 가 다시 노출될
   수 있다. `_HIDE_FROM_ANSWER` 는 대체 열이 있는 별개 규칙으로 유지한다.

---

## §2 구현 순서 (지시서 우선순위 반영)

감점 축(SQL 원문 노출 · 투자권유 · 이름 날조)을 값 오류보다 먼저 닫는다.

1. 뿌리③+④ — W11 문구 · KG-008 날조 · Y16 값+권유  ← **최우선**
2. 뿌리② — W11 값
3. 뿌리⑤ — Z13
4. 뿌리①-A — S4·T14·V12·W5
5. 뿌리①-B — KG-018·W2·Y11
6. 뿌리⑥ — Y7·Z10
7. 뿌리⑦ — 예산 남으면

---

## §3 결과

전 커밋에서 매번 `pytest -q`(전체) · `tests/test_snapshot_round6.py`(동결선) · `eval/run_gold_check.py` 를 돌렸다.
최종: **345 통과 · 동결선 통과 · gold 147/147**. `git push` · 배포는 하지 않았다.

| 뿌리 | 항목 | 구현/보류 | 커밋 | 회귀 테스트 | 동결선 | (b) 예측 충돌이 실제로 났나 |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| ③+④ | S′뒤·G4·B-4′·B-5 | ✅ 구현 | `fbf0084` | `test_answer_surface_rules` · `test_zero_row_reason_never_leaks_sql` | 통과 | 아니오. R3 의 `prfd_attr_cds` 숨김은 별개 분기로 남겨 예측대로 무사 |
| ② | S′ 앞 (W11 값) | ✅ 구현 | `171956d` | `test_fund_key_column_correction` | 통과 | 아니오 (V4 불변 확인) |
| ⑤ | G6 (Z13) | ✅ 구현 | `71666e8` | `test_precheck_parses_sql` | 통과 | **예.** 1차 구현이 EXPLAIN 실패를 전부 기각해 정상 JOIN 별칭 SQL 2건을 오탐 기각 → 문법 계열(`near "…"`·`unrecognized token`·`incomplete input`)로 좁혀 해소. (b) 의 "validate_sql 과 목적 중복" 예측이 맞았다 |
| ①-A | M′·R′ (S4·T14·V12·W5) | ✅ 구현 | `770b5f9` | `test_lookup_grouping_shape_invariant` | 통과 | **예.** 예측 #1 그대로 — 랭킹 경로(`ORDER BY 값컬럼`)와 이름 모드 COUNT 질의(3R D T11)를 가로채 기존 테스트 2건이 깨졌다. ‘정렬 축’·‘전체 집계’ 두 조건으로 좁혀 해소 |
| ①-B | G1 (KG-018) | ✅ 구현 | `368f396` | `test_base_population_post_chain` | 통과 | **예.** 예측 #2 그대로 — F6′(개별 조회 공모 주입)까지 넣자 동결선 W5·X18 이탈. **아래 보류 참조** |
| ⑥ | P′+G3 (Y7) | ✅ 구현 | `75e607b` | `test_axis_clause_preserved` | 통과 | 아니오. 다만 **처방이 뒤집혔다** — 아래 참조 |
| ⑦-a | G5 단일 집계 (X17) | ✅ 구현 | `b3e5fb1` | `test_positive_count_not_refused` | 통과 | 아니오 |
| ⑦-b | G2 설정연도 (KG-035·X19) | ✅ 구현 | `7cc7d10` | `test_estb_year_canonical` | 통과 | 아니오 |
| ⑦-c | G7 클래스 표기 (Z1) | ✅ 구현 | `b7d1273` | `test_class_notation_is_name_suffix` | 통과 | 아니오 |
| ⑦-d | F3 구성종목 (KG-028·Z8) | ✅ 구현 | `0568686` | `test_holdings_template_overrides_hcx_join` | 통과 | 아니오 |

### 🟡 보류 (구현하지 않음 · 이유 명시)

| 항목 | 왜 보류했나 | 되살리는 법 |
| :-- | :-- | :-- |
| **F6′** — 개별 조회 재작성 SQL 에 `prvo_pbff_desc='공모'` 주입 (W2 사모 3펀드 혼입 · Y11 판매완료 혼입) | 구현했다가 되돌렸다. 동결선 **W5·X18** 의 WHERE 텍스트가 바뀐다 — 행수(7·20)·조립기·답변 머리는 전부 불변이라 값 회귀가 아니지만, 지시서의 🔴 동결선 우선 원칙을 따랐다 | `ensure_fund_base_population` 의 `if post and (_has_name_filter…)` 조기 반환 한 줄을 지우고 동결선을 `SNAPSHOT_WRITE=1` 로 갱신 |
| **G1 의 ETF 절반** — `domestic_etfs`: `pd_sale_yn=1` 기본모수 | 이 코드베이스에 ETF 기본모수 가드가 **아예 없다**(`grep pd_sale_yn src/runtime` → 0건). 새 축을 세우는 일이라 ETF ✅ 문항 전부가 (c) 후보가 되고, 6R 의 실측 결함(KG-018·Z18·W2·Y11)은 전부 펀드 쪽이다 | 별도 라운드에서 ETF 문항 전수 실측 후 |
| **G3 의 치환 절반** — 주입 후 HCX 가 쓴 사전 밖 축 절 제거(Z10 `zrin_btyp_nm='인도주식형'`) | 주입(Y7)만으로 필수 항목이 닫힌다. 제거는 `check_values` 가 왜 사전 밖 값을 통과시켰는지부터 봐야 하고, 잘못 만지면 정당한 값을 지운다 | `guard.check_values` 의 `zrin_btyp_nm` vocab 커버리지 확인이 선행 |
| **G5 의 다열·다행 절반** + `SELECT` 절 리터럴 기각(X22 `COALESCE(…, '국민은행')`) | 단일 집계 갈래(X17)만 구현했다. 다열 사후 대조는 조립기 전면 개편이고, SELECT 리터럴 기각은 `'억원'`·`'(미수록)'` 같은 정당한 리터럴과 구분 규칙이 필요하다 | 다음 라운드 |
| **Z18 (F1 후속)** | 뿌리 어디에도 안 걸린다 — HCX 가 `zrin_btyp_nm IN ('주식형','해외주식형')` 을 지어낸 것이고, 라벨 충돌 노드('ETF')의 이름 폴백을 목록 경로에 주는 KG 층 작업(이월표 `F1 후속`)이다 | KG 층 라운드 |

### 🔴 처방을 뒤집은 곳 — 뿌리⑥ (P′)

6R 보고서의 P′ 는 *"운용사 확정식이 부가 절을 전부 버렸다 → 보존하라"* 였다. 6R 트레이스를 원본 대조한 결과
`ensure_fund_manager_ranking` 의 **폐기 notes 가 비어 있었다**(트레이스 9줄의 `[Guard] 운용사 집계 확정식` 뒤에
`· 부가 절 폐기` 접미가 없다). 즉 확정식이 버린 게 아니라 **HCX 가 애초에 `주식형` 절을 안 썼다.**
따라서 처방은 '보존' 이 아니라 '주입' 이고, 이는 KG §③ **G3 과 같은 규칙**이다 — 두 심사관의 서로 다른 항목이
한 뿌리로 접힌 자리다. 실측으로 gold 3열 전부 일치(69,336/142 · 46,152/28 · 41,914/18).
</content>
