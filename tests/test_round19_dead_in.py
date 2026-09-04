# -*- coding: utf-8 -*-
"""19R — IN 목록의 죽은 값이 정답 SQL 을 죽이던 자리 (2026-09-04 KG-012).

    zrin_ptn_nm = '중국주식' AND zrin_btyp_nm IN ('해외주식형','국내외혼합')

`'국내외혼합'` 은 `ovrs_fd_desc` 의 값이라 `zrin_btyp_nm` 에선 0행에 매칭된다. 그런데 값 검사가
이걸 기각해 답변이 통째로 죽었다 — 실측하면 그 SQL 이 낸 205펀드/522클래스가 **정답이었다**.

안전성: OR 가지에서 0행 매칭 값을 빼는 것은 결과를 바꾸지 않는다(결과 보존적).
불개입: 유효값이 하나도 안 남으면 손대지 않는다 — 빼는 순간 모수가 넓어져 조용한 오답이 된다.
"""
import pytest

from src.runtime import guard
from src.runtime.loader import db_path, load_context

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

W = "SELECT COUNT(*) FROM public_funds WHERE {} LIMIT 30"


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def test_drops_only_dead_literal(ctx):
    sql = W.format("zrin_ptn_nm='중국주식' AND zrin_btyp_nm IN ('해외주식형','국내외혼합')")
    out, dead = guard.prune_dead_in_literals(sql, ctx)
    assert dead == ["국내외혼합"]
    assert "'해외주식형'" in out and "국내외혼합" not in out
    assert not guard.check_values(out, ctx), "보정 뒤에는 값 검사가 통과해야 한다"


def test_result_is_preserved(ctx):
    """뺀 값이 0행 매칭이므로 행 수가 같아야 한다 — 이 등식이 이 가드의 안전성 근거다."""
    from src.runtime.pipeline import connect_readonly
    base = "sale_yn='판매중' AND prvo_pbff_desc='공모' AND zrin_ptn_nm='중국주식'"
    sql = W.format(base + " AND zrin_btyp_nm IN ('해외주식형','국내외혼합')")
    out, dead = guard.prune_dead_in_literals(sql, ctx)
    assert dead
    con = connect_readonly()
    try:
        before = con.execute(sql).fetchone()[0]
        after = con.execute(out).fetchone()[0]
    finally:
        con.close()
    assert before == after == 522, f"결과가 바뀌었다: {before} → {after}"


@pytest.mark.parametrize("where, why", [
    ("zrin_btyp_nm IN ('국내외혼합','해외')", "유효값이 하나도 안 남으면 기각이 옳다"),
    ("zrin_btyp_nm = '국내외혼합'", "단독 등호는 빼면 모수가 넓어진다"),
    ("zrin_btyp_nm IN ('해외주식형','주식형')", "전부 유효하면 할 일이 없다"),
])
def test_no_touch(ctx, where, why):
    sql = W.format(where)
    out, dead = guard.prune_dead_in_literals(sql, ctx)
    assert (out, dead) == (sql, []), why


def test_kg012_end_to_end(ctx):
    """문항 수준 — 2차에서 기각당한 SQL 이 이제 정답을 낸다."""
    from src.runtime.pipeline import answer_question
    sql = ("SELECT COUNT(DISTINCT " + guard.FUND_KEY_EXPR + ") AS \"펀드수\", COUNT(*) AS \"클래스수\" "
           "FROM public_funds WHERE zrin_ptn_nm = '중국주식' AND prvo_pbff_desc = '공모' "
           "AND sale_yn = '판매중' AND zrin_btyp_nm IN ('해외주식형','국내외혼합') LIMIT 30")

    class P:
        def plan_sql(self, q, g):
            return sql

        def compose_answer(self, q, rows, answer_rules=""):
            return "HCX-CALLED"

    r = answer_question("KG-012", "해외주식형 중에서 중국주식 유형인 공모펀드는 몇 개야?", planner=P(), ctx=ctx)
    assert "IN 목록 정리" in r.think_trace, "보정 가드가 발동하지 않았다"
    assert "205" in (r.answer or "") and "522" in (r.answer or ""), r.answer
