# -*- coding: utf-8 -*-
"""20R — 배제 낱말이 정반대 조건으로 나가던 자리 (FND-006, 1·2·3차 내리 ❌).

    "MMF를 제외하고 순자산이 가장 큰 공모펀드 5개 알려줘"
    → WHERE zrin_ptn_nm = 'MMF'          ← 정반대다

접지는 성공했고(MMF 를 찾았다) **연산자만 뒤집혔다.** 답이 MMF 목록이 되었는데 숫자가
그럴듯해 오답인 줄도 모른다 — 틀린 답을 자신 있게 내놓는 부류다.
`query_rules.부정조건` 이 문안까지 정확히 적어 두었는데도 세 회차 모두 안 지켜졌다.

🔴 배제 대상은 **데이터에서 유도**한다. 한 축만 걸면 샌다 — 2026-09-05 실측:
   `zrin_ptn_nm <> 'MMF'` 만 걸면 한국투자법인용달러MMF 1.04조가 2위로 올라온다
   (그 펀드의 zrin_btyp_nm 은 '외화 MMF'). 세 축 전수에서 유도해야 정답과 일치한다.
"""
import pytest

from src.runtime import guard
from src.runtime.loader import connect_readonly, db_path, load_context
from src.runtime.pipeline import answer_question

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

Q = "MMF를 제외하고 순자산이 가장 큰 공모펀드 5개 알려줘"
SQL = ("SELECT itm_no, TRIM(itm_nm) AS itm_nm, fd_nast_suma FROM public_funds "
       "WHERE zrin_ptn_nm = 'MMF' AND sale_yn = '판매중' AND prvo_pbff_desc='공모' "
       "ORDER BY fd_nast_suma DESC LIMIT 5")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def test_exclusion_is_derived_from_every_named_axis(ctx):
    out, tok = guard.ensure_excluded_value(SQL, Q, ctx)
    assert tok == "MMF"
    for col in ("or_attr_desc", "zrin_btyp_nm", "zrin_ptn_nm"):
        assert f"COALESCE({col},'') NOT IN" in out, f"{col} 축이 빠졌다 — 한 축만 걸면 샌다"
    assert "외화 MMF" in out, "표기 변형(외화 MMF)을 유도하지 못했다"
    assert "zrin_ptn_nm = 'MMF'" not in out, "같은 낱말의 긍정 조건이 남았다"
    assert " AND AND " not in out and "WHERE AND" not in out, "접속사가 깨졌다"


def test_excluded_rows_are_actually_gone(ctx):
    out, _ = guard.ensure_excluded_value(SQL, Q, ctx)
    con = connect_readonly()
    try:
        names = [r[1] for r in con.execute(out).fetchall()]
    finally:
        con.close()
    assert names and not any("MMF" in n.upper() for n in names), names
    assert names[0].startswith("피델리티글로벌테크놀로지"), names


@pytest.mark.parametrize("q, why", [
    ("MMF 중에서 순자산이 가장 큰 공모펀드 3개 알려줘", "배제 낱말이 없으면 불개입 — FND-007 은 MMF 를 묻는다"),
    ("순자산이 가장 큰 공모펀드 5개 알려줘", "배제 낱말 없음"),
])
def test_no_touch(ctx, q, why):
    assert guard.ensure_excluded_value(SQL, q, ctx) == (SQL, None), why


def test_end_to_end_survives_the_type_axis_injection(ctx):
    """🔴 `유형 축 주입` 이 질문의 'MMF' 를 긍정 조건으로 **되돌려 넣는다** — 배제는 그 뒤에 못 박아야 한다."""
    class P:
        def plan_sql(self, q, g):
            return SQL

        def compose_answer(self, q, rows, answer_rules=""):
            return "HCX-CALLED"

    r = answer_question("FND-006", Q, planner=P(), ctx=ctx)
    ans = r.answer or ""
    assert "HCX-CALLED" not in ans and "배제 조건 확정식" in r.think_trace
    assert "MMF" not in ans, ans
    assert "피델리티글로벌테크놀로지" in ans, ans
