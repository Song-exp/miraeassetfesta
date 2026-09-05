# -*- coding: utf-8 -*-
"""프리즈 전 마지막 셋 — 답을 바꾸지 않고 덧붙이는 자리.

KG-018: '…도 있어?' 존재 질의에 목록 SELECT → 같은 WHERE 의 펀드수·클래스수 집계 + '네, 있습니다'.
KG-031: '역외까지 포함하면' → 두 수를 따로 말한 뒤 합산 한 줄.
DOM-13: 연환산 부재 즉답에 물은 기간의 누적값(펀드 단위·대표 클래스 MAX)을 병기.
"""

import pytest

from src.runtime.loader import load_context
from src.runtime.pipeline import absent_period_value_note, answer_question, ensure_exist_count


@pytest.fixture(scope="module")
def ctx():
    return load_context()


RAW_LIST = ("SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS cnt, prfd_attr_cds FROM public_funds WHERE sale_yn = '판매중' "
            "AND prvo_pbff_desc = '공모' AND ','||prfd_attr_cds||',' LIKE '%,C102,%' GROUP BY itm_no HAVING cnt > 1 LIMIT 30")


def test_존재_질의의_목록_SELECT_를_개수_집계로(ctx):
    out, fixed = ensure_exist_count(RAW_LIST, "단위형이면서 개방형인 공모펀드도 있어?")
    assert fixed and out.startswith("SELECT COUNT(DISTINCT") and '"펀드수"' in out and '"클래스수"' in out
    assert "GROUP BY" not in out.upper() and "HAVING" not in out.upper()
    assert "LIKE '%,C102,%'" in out                       # WHERE 는 그대로


@pytest.mark.parametrize("q, sql", [
    ("단위형 공모펀드 알려줘", RAW_LIST),                                                    # 존재 어미 없음
    ("단위형 펀드도 있어?", "SELECT COUNT(DISTINCT itm_no) FROM public_funds LIMIT 30"),      # 이미 집계
    ("순자산 큰 펀드도 있어?", "SELECT itm_no, fd_nast_suma FROM public_funds ORDER BY fd_nast_suma DESC LIMIT 5"),  # 랭킹
])
def test_존재_집계_불개입(q, sql, ctx):
    assert ensure_exist_count(sql, q) == (sql, False)


def test_존재_질의_전_구간은_예_아니오로_시작한다(ctx):
    class P:
        def plan_sql(s, q, g): return RAW_LIST
        def compose_answer(s, q, rows, a=""): return "[HCX]"
    r = answer_question("T", "단위형이면서 개방형인 공모펀드도 있어?", planner=P(), ctx=ctx)
    assert r.answer.startswith("네, 있습니다 — ") and "클래스" in r.answer


def test_역외_포함_질문엔_합산_한_줄(ctx):
    sql = ("SELECT COUNT(*) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080029' "
           "AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30")
    class P:
        def plan_sql(s, q, g): return sql
        def compose_answer(s, q, rows, a=""): return "[HCX]"
    r = answer_question("T", "피델리티가 운용하는 공모펀드는 역외펀드까지 포함하면 몇 개야?", planner=P(), ctx=ctx)
    assert "별도 법인이라 이 수에 포함하지 않았습니다" in r.answer      # 고지는 그대로
    assert "역외펀드까지 포함하면" in r.answer and "153개" in r.answer


def test_연환산_부재_즉답에_누적값을_붙인다(ctx):
    note = absent_period_value_note("미래에셋코어테크 펀드 3년 수익률을 연평균으로 알려줘", [],
                                    "온톨로지 ABSENT — public_funds 에 (연평균·연환산 수익률) 속성 없음")
    assert note and "3년 누적 수익률" in note and "190.99%" in note and "대표 클래스 기준 MAX" in note


def test_기간이나_상품이_없으면_붙이지_않는다(ctx):
    reason = "온톨로지 ABSENT — public_funds 에 (연평균·연환산 수익률) 속성 없음"
    assert absent_period_value_note("연평균 수익률 높은 펀드 알려줘", [], reason) is None      # 상품 없음
    assert absent_period_value_note("미래에셋코어테크 펀드 연환산 수익률", [], reason) is None    # 기간 없음
    assert absent_period_value_note("미래에셋코어테크 3년 수익률", [], "다른 사유") is None      # 연환산 사유 아님
