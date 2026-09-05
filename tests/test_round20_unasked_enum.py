# -*- coding: utf-8 -*-
"""20R — 질문이 부르지 않은 값이 열거 조건에 끼어들던 자리 (2026-09-05 DOM-05).

    "파생상품 유형 공모펀드 중 순자산 큰 3개 알려줘"
    → or_attr_desc IN ('재간접', '파생상품')
                        ↑ 질문에 없다

1위가 피델리티글로벌테크놀로지(**재간접형**) 12,196억으로 바뀌었다 — 정답 1위는
NH-Amundi코리아2배레버리지(파생형) 7,333억이다. 머리줄에 '재간접·파생상품 기준' 이라 적히긴
하지만 **묻지 않은 것을 답한 것**이다.

🔴 발동은 좁다 — 질문이 그 목록의 값을 **하나라도 이름으로 불렀을 때만** 나머지를 걷는다.
하나도 안 불렀으면 총칭어 질의이고(`혼합형` → IN('주식혼합형','채권혼합형')은 `혼합형 확정식
치환` 이 일부러 넓힌 것이다) 건드리면 안 된다.
"""
import pytest

from src.runtime import guard
from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

W = "SELECT a FROM public_funds WHERE {} LIMIT 3"


def test_drops_the_unasked_value():
    out, dropped = guard.drop_unasked_enum_values(
        W.format("or_attr_desc IN ('재간접', '파생상품')"), "파생상품 유형 공모펀드 중 순자산 큰 3개 알려줘")
    assert dropped == ["재간접"] and "'파생상품'" in out and "재간접" not in out


@pytest.mark.parametrize("where, q, why", [
    ("zrin_btyp_nm IN ('주식혼합형','채권혼합형')", "혼합형 펀드 알려줘",
     "🔴 총칭어 질의 — 혼합형 확정식이 일부러 넓힌 목록이라 건드리면 안 된다"),
    ("or_attr_desc IN ('재간접', '파생상품')", "재간접이랑 파생상품 펀드 알려줘", "둘 다 불렀으면 유지"),
    ("zrin_ptn_nm IN ('MMF')", "MMF 알려줘", "값이 하나뿐이면 걷을 게 없다"),
    ("itm_nm IN ('재간접','파생상품')", "파생상품 알려줘", "이름 컬럼은 대상이 아니다"),
])
def test_no_touch(where, q, why):
    sql = W.format(where)
    assert guard.drop_unasked_enum_values(sql, q) == (sql, []), why


def test_dom05_end_to_end():
    """1위가 정답으로 돌아온다 — HCX 0회."""
    ctx = load_context()
    sql = ("SELECT itm_no, TRIM(itm_nm) AS itm_nm, fd_nast_suma FROM public_funds "
           "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
           "AND or_attr_desc IN ('재간접', '파생상품') AND fd_nast_suma <> 0 "
           "ORDER BY fd_nast_suma DESC LIMIT 3")

    class P:
        def plan_sql(self, q, g):
            return sql

        def compose_answer(self, q, rows, answer_rules=""):
            return "HCX-CALLED"

    r = answer_question("DOM-05", "파생상품 유형 공모펀드 중 순자산 큰 3개 알려줘", planner=P(), ctx=ctx)
    ans = r.answer or ""
    assert "HCX-CALLED" not in ans
    assert "안 물은 값 제거" in r.think_trace
    assert ans.splitlines()[2].startswith("1. NH-Amundi코리아2배레버리지"), ans
    assert "재간접" not in ans, "묻지 않은 축이 답변에 남았다"
