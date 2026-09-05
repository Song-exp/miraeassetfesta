# -*- coding: utf-8 -*-
"""6차가 남긴 둘 — 정렬 없는 LIMIT 과 안 물은 개수 조건.

U14: `… HAVING fd_yr1_ern_r = MAX(fd_yr1_ern_r) LIMIT 3` — ORDER BY 가 아예 없어 상위 3개가 임의 3행이었다.
KG-018: `GROUP BY itm_no HAVING cnt > 1` — itm_no 는 고유키라 항상 0행. 질문은 개수를 물은 적이 없다.
"""

import pytest

from src.runtime.loader import load_context
from src.runtime.pipeline import drop_unasked_count_having, ensure_fund_rank_axis


@pytest.fixture(scope="module", autouse=True)
def _ctx():
    load_context()


def test_정렬_없는_LIMIT_에_질문의_축을_세운다():
    sql = ("SELECT itm_no, COUNT(*) AS c, fd_yr1_ern_r FROM public_funds WHERE sale_yn = '판매중' "
           "GROUP BY or_co_xtn_itt_cd HAVING fd_yr1_ern_r = MAX(fd_yr1_ern_r) LIMIT 3")
    out, fixed = ensure_fund_rank_axis(sql, "1년 수익률이 가장 높은 공모펀드 3개는 클래스가 몇 개씩이야?")
    assert fixed and "ORDER BY fd_yr1_ern_r DESC LIMIT 3" in out
    assert "HAVING fd_yr1_ern_r = MAX(fd_yr1_ern_r)" in out          # HAVING 은 안 건드린다


def test_LIMIT_도_없으면_불개입():
    sql = "SELECT itm_no, fd_yr1_ern_r FROM public_funds WHERE sale_yn = '판매중'"
    assert ensure_fund_rank_axis(sql, "1년 수익률이 가장 높은 펀드")[1] is False


def test_고유키_묶음의_개수_조건을_걷는다():
    sql = ("SELECT itm_no, COUNT(*) AS cnt FROM public_funds WHERE sale_yn = '판매중' "
           "GROUP BY itm_no HAVING cnt > 1 LIMIT 30")
    out, fixed = drop_unasked_count_having(sql, "단위형이면서 개방형인 공모펀드도 있어?")
    assert fixed and "HAVING" not in out.upper() and "GROUP BY itm_no" in out


def test_질문이_개수를_물었으면_그대로_둔다():
    sql = ("SELECT itm_no, COUNT(*) AS cnt FROM public_funds "
           "GROUP BY itm_no HAVING cnt > 1 LIMIT 30")
    for q in ("클래스가 2개 이상인 펀드 알려줘", "클래스가 여러 개인 펀드", "중복된 종목 찾아줘"):
        assert drop_unasked_count_having(sql, q)[1] is False, q


def test_분포_묶음에는_불개입():
    """운용사별·유형별 묶음의 HAVING 은 답의 축이다 — 고유 식별자 묶음일 때만 걷는다."""
    sql = ("SELECT zrin_btyp_nm, COUNT(*) AS cnt FROM public_funds "
           "GROUP BY zrin_btyp_nm HAVING cnt > 1 LIMIT 30")
    assert drop_unasked_count_having(sql, "유형별로 알려줘")[1] is False
