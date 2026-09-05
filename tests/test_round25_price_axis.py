# -*- coding: utf-8 -*-
"""25R — 가격 축 대체(#79)와 무효 컬럼 예산 오용(#78). 2026-09-05 밤 · 사용자 직접 테스트 2문항.

#79 "장내에서 실제 거래된 가격이 가장 비싼 채권이 뭐야?"
    → `ORDER BY eval_price DESC` (민평 평가단가). 1위로 나온 산금채07신복2000-0528-2 의 `exg_close_price` 는
      **0.0 = 장내 거래 없음**이었다. 질문이 '실제 거래된' 을 명시했는데 거래 이력이 0인 행을 1위로 냈고,
      머리줄의 '전체 17,689종목' 도 장내 등록 수지 거래된 종목 수(1,262)가 아니다.

#78 "100만원으로 살 수 있는 채권 추천해줘"
    → `buyable_quantity >= 1000000`. 두 겹으로 틀렸다: ① 주최 공지(8/24)로 무효 확정된 컬럼이고
      ② 뜻이 매수가능수량(잔량)이라 그 식은 '물량이 많이 남은 종목' 을 고른다. 모수 20,431 → 280 종목
      (98.6% 소실)인데 답변은 좁힌 사실을 밝히지 않았다. 값은 전부 실제 행이라 환각 검사에 안 걸린다.

과적합 점검 (이 파일이 검사한다):
 ① 새 가드를 세우지 않았다 — #71 이 만든 **정렬 축 혼동쌍 표**(_SORT_AXES)에 두 행을 얹었을 뿐이다.
 ② 사례가 아니라 규칙이다 — 가격 3축 전부(장내종가·매매단가·평가가)를 표로 갈랐고 DB 로 모수를 실측한다.
 ③ 형제 12문형을 회귀로 건다 — 발동해야 할 6개와 **불개입해야 할 6개**를 같은 표에서 본다.
 ④ 기존 226 gold 문항에 신규 개입·신규 기각이 0 인지 전수로 확인한다.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from src.runtime import gate
from src.runtime.loader import db_path, load_context, PROJECT_ROOT
from src.runtime.pipeline import (_bond_list_answer, domain_caveats, ensure_sort_axis,
                                  forbidden_column_use)

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

Q79 = "장내에서 실제 거래된 가격이 가장 비싼 채권이 뭐야?"
# 서버가 실제로 실행한 SQL (동률 2차 정렬 주입 전 형태)
SQL79 = ("SELECT pd_nm, eval_price FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 "
         "AND (pd_exg_mkt = '장내' AND eval_price > 0) ORDER BY eval_price DESC LIMIT 1")
# 서버가 실제로 실행한 SQL (#78)
SQL78 = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, applied_yield FROM domestic_bonds WHERE curr_cd = 'KRW' "
         "AND mat_dt >= 20260824 AND buyable_quantity >= 1000000 AND applied_yield > 0 "
         "GROUP BY pd_no ORDER BY 3 DESC LIMIT 5")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(db_path())
    yield c
    c.close()


# ── #79 ① 사고 재현 — 답이 고른 1위는 장내 거래가 없는 종목이었다 (DB 사실) ─────────────
def test_the_answered_top1_had_no_exchange_trade(con):
    row = con.execute("SELECT exg_close_price, eval_price FROM domestic_bonds "
                      "WHERE TRIM(pd_nm) = '산금채07신복2000-0528-2'").fetchone()
    assert row is not None
    assert row[0] == 0.0                      # 장내 종가 0 = 거래 없음
    assert round(row[1], 2) == 28944.36       # 답이 인용한 값 자체는 실제 평가가였다 — 값이 아니라 축이 틀렸다


# ── #79 ② 축 교정 — eval_price → exg_close_price · `> 0` · 기준일 동반 ────────────────
def test_traded_price_question_switches_axis():
    sql, changed = ensure_sort_axis(SQL79, Q79)
    assert changed
    assert "ORDER BY exg_close_price DESC" in sql
    assert "exg_close_price > 0" in sql                    # 0 = 거래 없음이라 모수에서 빠져야 한다
    assert "exg_close_price_base_dt" in sql.split("FROM")[0]   # 기준일 병기 (규칙 장내종가)


def test_corrected_sql_gives_the_real_top1(con):
    sql, _ = ensure_sort_axis(SQL79, Q79)
    (name, _ev, price, base_dt) = con.execute(sql).fetchone()
    assert name.strip() == "메리츠캐피탈 256-4"
    assert price == 10135.0
    assert base_dt.strip() == "20260821"


def test_population_is_traded_bonds_not_listed_bonds(con):
    """머리줄의 모수도 축을 따라간다 — 17,689(장내 등록)가 아니라 1,262(장내 거래 실재)."""
    listed = con.execute("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd='KRW' "
                         "AND mat_dt >= ? AND pd_exg_mkt='장내' AND eval_price > 0", (20260824,)).fetchone()[0]
    traded = con.execute("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd='KRW' "
                         "AND mat_dt >= ? AND exg_close_price > 0", (20260824,)).fetchone()[0]
    assert (listed, traded) == (17689, 1262)


# ── #79 ③ 형제 12문형 — 발동 6 · 불개입 6 ────────────────────────────────────────────
@pytest.mark.parametrize("question, axis", [
    ("장내에서 실제 거래된 가격이 가장 비싼 채권이 뭐야?", "exg_close_price"),
    ("실제 거래된 가격이 가장 비싼 채권 알려줘", "exg_close_price"),      # 시장 미명시 + 거래 어휘 = 장내 종가
    ("장내 체결 가격 높은 순으로 5개", "exg_close_price"),
    ("장내에서 실제 거래된 가격이 가장 싼 채권", "exg_close_price"),      # 방향이 반대여도 축은 같다
    ("장외에서 실제 거래된 가격이 가장 비싼 채권", "trade_price"),        # '장외' 가 일반 어휘 가지를 잠근다
    ("매매단가 가장 높은 채권", "trade_price"),
    # ↓ 불개입 — 질문이 축을 다르게 못박았거나 가격 축이 아니다
    ("평가가 가장 높은 채권", "eval_price"),
    ("민평 평가단가 높은 순 5개", "eval_price"),
    ("수익률이 가장 높은 채권은 뭐야?", "eval_price"),
    ("표면금리 높은 순 5개", "eval_price"),
    ("발행잔액 큰 3개", "eval_price"),
    ("장내 종가와 평가가 차이가 큰 채권", "eval_price"),                 # 두 축을 함께 말하면 불개입
])
def test_price_axis_siblings(question, axis):
    sql, _ = ensure_sort_axis(SQL79, question)
    assert f"ORDER BY {axis} " in sql + " ", question


def test_count_query_is_untouched():
    """개수 질의엔 정렬 축 가드가 애초에 개입하지 않는다 (COUNT 불개입 — 기존 조건)."""
    s = "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE pd_exg_mkt='장내'"
    assert ensure_sort_axis(s, "장내에서 거래되는 채권 몇 종목이야?") == (s, False)


# ── #79 ④ 조립 — 장내종가는 기준일과 한 덩어리, 그리고 '오늘 시세 아님' 고지 ────────────
def test_answer_pairs_close_price_with_its_base_date():
    rows = ("pd_nm | eval_price | exg_close_price | exg_close_price_base_dt\n"
            "메리츠캐피탈 256-4 | 10123.56 | 10135.0 | 20260821")
    sql, _ = ensure_sort_axis(SQL79, Q79)
    a = _bond_list_answer(sql, rows, 1, Q79)
    assert a and "장내종가 10135.0(종가 기준일 2026-08-21)" in a


def test_close_price_freshness_caveat():
    sql, _ = ensure_sort_axis(SQL79, Q79)
    notes = domain_caveats(sql, "", Q79)
    assert any("마지막으로 체결된 날의 가격" in n for n in notes)
    assert not any("마지막으로 체결된 날" in n for n in domain_caveats(SQL79, "", "평가가 높은 채권"))


# ── #78 ① 무효 컬럼은 기각하고 사유로 대체 경로를 돌려준다 ────────────────────────────
def test_buyable_quantity_is_rejected_with_a_usable_reason(ctx):
    why = forbidden_column_use(SQL78, ctx)
    assert why
    assert "mat_dt >= 20260824" in why           # 재생성이 갈 자리를 사유가 알려 준다
    assert "최소투자금액" in why                 # 금액 조건을 다른 컬럼으로 옮겨 만들지 않게
    # 같은 SQL 에서 그 절만 빼면 통과한다 — 기각은 컬럼 하나에만 걸린다
    assert forbidden_column_use(SQL78.replace("AND buyable_quantity >= 1000000 ", ""), ctx) is None


def test_forbidden_columns_come_from_yaml_and_are_table_scoped(ctx):
    assert set(ctx.forbidden_cols["domestic_bonds"]) == {
        "buyable_quantity", "avg_annual_tax_yield", "dirty", "ndy_dirty"}
    # 🔴 채권 선언이 다른 테이블 SQL 을 기각하면 안 된다 (2026-09-04 DOM-03 과 같은 함정)
    assert forbidden_column_use("SELECT itm_nm FROM public_funds WHERE fd_yr1_ern_r > 0 LIMIT 5", ctx) is None
    # 코드 상수(펀드 2컬럼)는 이관 전이라 그대로 살아 있다 — ctx 없이도 잡힌다
    assert forbidden_column_use("SELECT itm_nm FROM public_funds WHERE fd_wk1_ern_r > 0 LIMIT 5")


# ── #78 ② 좁히지 않은 이유를 답변이 밝힌다 (되묻지 않는다 — 되물어도 데이터가 안 생긴다) ──
@pytest.mark.parametrize("question, fires", [
    ("100만원으로 살 수 있는 채권 추천해줘", True),
    ("5천만원으로 살 만한 채권 알려줘", True),
    ("1억 정도 투자하려는데 어떤 채권이 좋아?", True),
    ("예산에 맞는 채권 추천해줘", True),
    ("발행잔액 1000억 이상인 채권 알려줘", False),      # 채권의 규모지 사용자의 예산이 아니다
    ("총발행액 500억 넘는 회사채", False),
    ("수익률 5% 넘는 채권 추천해줘", False),
])
def test_budget_note_fires_only_on_budget_questions(question, fires):
    notes = domain_caveats("SELECT pd_nm FROM domestic_bonds LIMIT 5", "", question)
    assert any("금액으로는 좁히지 않았습니다" in n for n in notes) is fires, question


# ── 과적합 점검 ④ — 기존 gold 226문항에 신규 개입·신규 기각 0 ──────────────────────────
def _gold():
    for p in sorted((PROJECT_ROOT / "eval").glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if d.get("question"):
                    yield p.name, d["question"], d.get("gold_sql") or ""


def test_no_regression_on_existing_gold(ctx):
    touched, rejected = [], []
    for name, q, g in _gold():
        if not g:
            continue
        if ensure_sort_axis(g, q)[0] != g:
            touched.append((name, q))
        if forbidden_column_use(g, ctx):
            rejected.append((name, q))
    assert touched == [], touched
    assert rejected == [], rejected
