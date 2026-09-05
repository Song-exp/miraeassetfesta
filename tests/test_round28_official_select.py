# -*- coding: utf-8 -*-
"""OFFICIAL-002(주최 공식 문항)가 핵심 34 재점검에서 거절로 떨어졌다 — 세 겹으로 막는다.

① 유일 근사 치환이 별칭 붙은 참조(e.mother_fund_names)를 건너뛰던 정규식.
② SELECT 목록에만 있는 환각 컬럼(ext_fund_page_id)은 항목만 걷는다 — 표시 열은 모수를 바꾸지 않는다.
③ 재생성까지 실패해도 이름이 지목한 상품이 실재하면 수록 항목 조회로 대체한다.
+ DOM-06: A·C 클래스 보수 비교 고지는 질문으로 판정한다.
"""

import pytest

from src.runtime.loader import load_context
from src.runtime.pipeline import answer_question, domain_caveats, drop_hallucinated_select_items

RAW = ("SELECT DISTINCT e.ext_fund_page_id, e.itm_no, e.mother_fund_names, e.class_desc_ko, e.total_fee_pct "
       "FROM public_funds p JOIN ext_fund_page e ON e.itm_no = p.itm_no "
       "WHERE p.itm_nm LIKE '%국민성장%' AND p.sale_yn = '판매중' AND p.prvo_pbff_desc = '공모'")
Q = "국민성장펀드의 구조와 투자전략 동향 등 찾아서 알려줘"


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def test_SELECT_에만_있는_환각_컬럼은_항목만_걷는다(ctx):
    out, dropped = drop_hallucinated_select_items(RAW, ctx)
    assert "ext_fund_page_id" in dropped and "ext_fund_page_id" not in out
    assert "e.itm_no" in out and "e.total_fee_pct" in out
    assert "WHERE p.itm_nm LIKE '%국민성장%'" in out                 # 조건은 그대로


def test_WHERE_에도_쓰인_컬럼은_걷지_않는다(ctx):
    sql = "SELECT itm_no, asset_class FROM public_funds WHERE asset_class = 'X' LIMIT 30"
    assert drop_hallucinated_select_items(sql, ctx) == (sql, [])         # 환각 술어 가드의 몫


def test_전부_환각이면_불개입(ctx):
    sql = "SELECT foo_x, bar_y FROM public_funds LIMIT 30"
    assert drop_hallucinated_select_items(sql, ctx) == (sql, [])


def test_OFFICIAL_002_원문이_실행까지_간다(ctx):
    class P:
        def plan_sql(s, q, g): return RAW
        def compose_answer(s, q, rows, a=""): return "[HCX]"
    r = answer_question("OFFICIAL-002", Q, planner=P(), ctx=ctx)
    assert "[Execute]" in r.think_trace and "mother_fund_names_raw" in r.sql
    assert "답변을 제공하지 못했습니다" not in (r.answer or "")


def test_두_번_기각돼도_실재_상품이면_수록_항목으로(ctx):
    """WHERE 에 걷을 수 없는 환각 술어를 두 번 내면 종전엔 거절 — 이름이 지목한 상품이 있으면 수록 항목 조회."""
    bad = "SELECT itm_no FROM public_funds WHERE nonexistent_col = 'x' AND itm_nm LIKE '%국민성장%' LIMIT 30"
    class P:
        def plan_sql(s, q, g): return bad
        def compose_answer(s, q, rows, a=""): return "[HCX]"
    r = answer_question("OFFICIAL-002", Q, planner=P(), ctx=ctx)
    assert "수록 항목 조회로 대체" in r.think_trace and "[Execute]" in r.think_trace


def test_DOM06_고지는_질문으로_판정(ctx):
    q = "미래에셋코어테크 펀드는 A클래스와 C클래스 중 어느 쪽이 보수가 낮아?"
    notes = domain_caveats("SELECT or_co_rwrd_r FROM public_funds LIMIT 30", "or_co_rwrd_r\n7.2", q)
    assert any("선취 수수료" in n for n in notes)
    assert not any("선취 수수료" in n for n in domain_caveats("SELECT itm_no FROM public_funds LIMIT 30", "itm_no\nX", "순자산 큰 펀드"))
