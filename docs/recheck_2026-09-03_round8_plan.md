# 8라운드 수리 — 간섭 지도 (2026-09-03)

> 입력: `docs/recheck_2026-09-03_round7.md` §③(재검 17항) + `docs/kg_structure_probe_round5_2026-09-03.md` §③(KG 부류 A~P).
> 🔴 경계: `ontology/**` · `scripts/build_ontology.py` **무변경**. 전부 `src/runtime/pipeline.py` 안에서 닫는다.
> 동결선 `tests/test_snapshot_round6.py` — 값 계열(`rows`·`assembler`·`answer_head`·`route`·`nodes`) 불변이 조건.
> `where` 문자열만 바뀌면 근거를 적고 갱신(7R 선례).

## 실측으로 확정한 두 뿌리 (구현 전 원본 대조)

### 뿌리 α — `_hide_answer_columns` 가 열을 지우면 `label_code_columns` 가 arity 검사에서 무음 종료
`pipeline.py` 5152-5158 호출 순서 · 1623-1624 `if len(items) != len(cols): return rows, []`.
KG-008 은 SELECT 4항목 중 `수탁금액`(원값)이 숨김으로 지워져 헤더 3열 → 표기 가드 통째로 꺼짐 → HCX 가
`trim(trusc_xtn_itt_cd) AS 수탁회사명` 별칭만 보고 운용사 이름 3개 날조. AA16 은 숨김이 안 걸려서 통과.
**트레이스에 아무 흔적도 안 남는다** — 7R 수리가 실행조차 안 된 것으로 보인 이유.

### 뿌리 β — `guard.split_conjuncts` 가 괄호 안으로 안 들어가고, `ensure_fund_base_population` 은 원 조건을 괄호로 감싼다
`ensure_fund_base_population` L530: `WHERE {cond} AND ({body})` — 원 WHERE 전체가 **괄호 한 덩어리**가 된다.
`ensure_fund_holdings_template` 의 preds 루프는 그 덩어리 안에 보유테이블 컬럼(`h_only` = `weight_pct`·`grp`·
`or_co`·`bas_dt`…)이 하나라도 있으면 **덩어리 통째로 버린다** → 이름 필터가 함께 사라진다.
Z7·AA18 실측: preds 가 `sale_yn='판매중' AND prvo_pbff_desc='공모'` 둘만 남아 전 우주 순자산 1위 펀드의 종목을 답했다.
같은 루프가 `ensure_fund_manager_ranking` 에도 있다(잠재 동형 결함).

## 항목표

| # | (a) 부류 → 일반 규칙 | (b) 닿는 층 / 충돌 가능 지점 → 회귀 테스트 이름 | (c) 경로가 바뀔 수 있는 기존 ✅ |
| :-: | :-- | :-- | :-- |
| 1 | **KG 부류 D** — Answer 가드는 순서에 무관하게 각자 걸린다. 표기(`label_code_columns`)를 **먼저**, 숨김(`_hide_answer_columns`)을 나중에. 표기 가드가 전제 때문에 스킵되면 `[Guard] … 적용 불가(사유)` 를 트레이스에 남긴다 | 조립 `pipeline.py` 5152-5158 · 1609-1643 / 충돌: 숨김이 표기된 값(`이름(코드)`)을 못 알아볼 위험 → 숨김은 **헤더명**으로 판정하므로 무관 → `test_answer_guards_independent` | KG-008(❌) · X13 · X14 · AA16 · Z21 · AA15. 동결선은 HCX 경로의 answer 를 안 찍으므로(가짜 플래너 "HCX") 영향 없어야 한다 |
| 2 | **KG 부류 A** — ① 술어 필터는 괄호 그룹 안으로 들어간다(최상위 OR 없는 그룹만 평탄화) ② 구성종목 확정식 서브쿼리에 **펀드 특정 술어**(이름 LIKE·펀드키 핀)가 없으면 `name_token` 으로 되살리고, 그래도 없으면 확정식을 적용하지 않는다(오거절이 남의 펀드 값보다 낫다) | SQL 가드 `ensure_fund_holdings_template` + 새 헬퍼 `_flat_conjuncts` (같은 루프를 쓰는 `ensure_fund_manager_ranking` 에도 적용 — 새 가드 안 만듦) / 충돌: 평탄화가 `(a OR b)` 를 쪼개면 의미 파괴 → OR 있는 그룹은 평탄화 금지 → `test_holdings_template_keeps_name` · `test_flat_conjuncts_keeps_or_group` | Z7·AA18(❌ 거짓 값). 운용사 집계 ✅(T1·V5·Y6·Y7·U7) — 평탄화로 부가 절이 **더 많이** 보존되는 방향이라 값 변동 감시 |
| 3 | **KG 부류 A-b** — 라우팅이 `public_funds` 인 구성종목 질의는 HCX 가 어느 테이블로 새어 나갔든 확정식으로 교체한다(현행은 `FROM public_funds` 일 때만) | SQL 가드 `ensure_fund_holdings_template` 진입조건 + `_apply_sql_guards(tables=…)` / 충돌: ETF 구성종목 질의(라우팅 `domestic_etfs`)를 펀드 템플릿으로 덮으면 회귀 → `tables == ['public_funds']` 로만 게이트 → `test_holdings_template_on_etf_leak` | X1·X2·AA19·KG-028(전부 ❌ 오거절). ETF ✅(V7·W10·AA22 등)은 라우팅이 달라 불개입 |
| 4 | **KG 부류 C** — 잔여 고유명 토큰은 **라벨+잔여 결합형이 DB 에 실재하면 그쪽을 쓴다**(현행은 잔여만 3자 이상이면 즉시 채택). 접두가 붙어 계열 펀드(차이나·글로벌) 오매칭이 사라진다 | Ground `residual_name_token` L4033-4040 (이미 있는 `_name_chunk_exists` 분기를 앞으로 당김 — 새 규칙 아님) / 충돌: 토큰이 바뀌면 개별 조회 머리줄 문자열(`'X' 이름의 …`)이 바뀐다 = 동결선 `answer_head` → `test_residual_token_prefers_whole` | X18(🔴 회귀). 감시: W2·U10·T6·Y14·V4·Z7·KG-028 — **동결선 `answer_head` 가 깨지면 되돌리고 보고** |
| 5 | **KG 부류 C-b** — 이름을 답에 싣는 SQL 은 `itm_nm` 을 SELECT 에 포함시켜 `verify_product_names` 사전이 비지 않게 한다. 사전이 비어 교정을 못 하면 트레이스에 남긴다 | SQL 가드 `ensure_fund_evidence_columns` 계열 + 조립 `verify_product_names` / 충돌: SELECT 열 추가가 `_lookup_answer` 헤더 검사(`cols[:4] != _LOOKUP_HEAD`)를 깰 수 있음 → 묶기 가드 산출 SQL 에는 불개입 → `test_name_dict_trace` | X18. R3·S7 목록 계열(이미 itm_nm 있음 — 불개입) |
| 6 | **재검 ③-1 / 부류 R″** — `_LOOKUP_ROW_UNIT` 불개입은 **질문 낱말만** 본다. `and not m_grp`(모양 조건) 삭제 | SQL 가드 `ensure_fund_lookup_grouping` L1142 / 충돌: '클래스' 열거 경로(T6·R6·S5)가 묶기로 들어옴 → `test_lookup_grouping_class_no_shape` | U3(❌). 감시: T6·R6·S5·V13·W3 |
| 7 | **재검 ③-9 / 부류 B-5′** — 답변 표면 필터에 (c) `gate.DATA_CUTOFF` 와 다른 기준일 문장 · (d) 실제 SQL 과 다른 집계 방법론 문장 · 추측 문장을 더한다(제거만, 대체 생성 없음) | 조립 `_DISCLAIMER` 사전 / 충돌: 정당한 기준일 문장(조립기가 굽는 `기준일 2026-08-24`)까지 지우면 대형 회귀 → **다른 날짜일 때만** 매칭 → `test_strip_wrong_cutoff` | S1·Y3·Y1. 감시: 기계 조립 답 전부(머리줄에 정본 기준일 포함) |
| 8 | **재검 ③-10 / 부류 F6″-b** — 랭킹 답변을 기계 조립으로 돌린다(SELECT 에 실린 클래스수를 반드시 옮기고, 순자산 축 MAX/SUM 을 기계 표기). HCX 를 안 부르므로 ③-9 의 꼬리 결함이 구조적으로 사라진다 | 조립 — 새 `_rank_answer` 를 `_list_answer` 형제로 (기존 `_manager_rank_answer`·`_list_answer` 와 헤더로 배타) / 충돌: `_list_answer`·`_lookup_answer` 와 발동 조건 겹침 → 헤더 집합으로 배타 판정 → `test_rank_answer_assembles` | R7·S1·V16·Y1·Y3·Y4·Y5·Y2·U13. 동결선의 `assembler` 마커가 `HCX` → 기계 조립으로 바뀌는 qid 가 있으면 **값 대조 후** 갱신 |

## 보류(이번 라운드에 손대지 않음) — 근거

- 재검 ③-2(T′ U6 축 확장 우선순위) · ③-3(F6″ Y11 `sale_yn` 완화 재실행) · ③-4/③-5(B-4″ 해외 ETF 통화·기본모수) ·
  ③-6(U′ 방언 치환) · ③-7(V′ 2단 질의 축) · ③-8(W1′ 근접 후보) · ③-11~③-16,
  KG 부류 B·E·F·G·H·I·J·K·L·M·N·O·P — 위 8항을 끝낸 뒤 예산이 남으면.
- **③-17 온톨로지 층 2건은 구현하지 않는다**(보고만). 두 심사관 모두 "온톨로지 변경 요구 0건" 을 명시했다.

## 검증 절차 (항목마다)

```bash
export PYTHONIOENCODING=utf-8
./.venv/Scripts/python.exe -m pytest tests/test_snapshot_round6.py -q   # 동결선
./.venv/Scripts/python.exe -m pytest -q                                 # 전체
./.venv/Scripts/python.exe eval/run_gold_check.py                       # gold 147/147
```
KG·ttl·yaml 무변경이므로 `build_ontology.py` 재실행 대상 아님.
