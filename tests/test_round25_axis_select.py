# -*- coding: utf-8 -*-
"""U14 서버 원문(API 로그 raw=) 이 드러낸 둘.

원문: SELECT itm_no, TRIM(itm_nm), COUNT(*) … ORDER BY 3 DESC LIMIT 5
① 질문이 지목한 축(fd_yr1_ern_r)이 SELECT 에 없으면 물러나지 않고 덧붙인 뒤 정렬을 세운다.
② 질문이 개수를 명시(3개)했으면 LIMIT 을 그 수로 맞춘다.
"""

import pytest

from src.runtime.loader import load_context
from src.runtime.pipeline import ensure_asked_topn, ensure_fund_rank_axis

RAW = ("SELECT itm_no, TRIM(itm_nm), COUNT(*) FROM public_funds WHERE sale_yn = '판매중' "
       "AND prvo_pbff_desc = '공모' AND fd_yr1_ern_r IS NOT NULL GROUP BY or_co_xtn_itt_cd, mtco_itm_no "
       "HAVING COUNT(*) >= 3 ORDER BY 3 DESC LIMIT 5")
Q = "1년 수익률이 가장 높은 공모펀드 3개는 클래스가 몇 개씩이야?"


@pytest.fixture(scope="module", autouse=True)
def _ctx():
    load_context()


def test_축_컬럼이_SELECT_에_없으면_덧붙이고_정렬을_세운다():
    out, fixed = ensure_fund_rank_axis(RAW, Q)
    assert fixed
    head = out[:out.upper().find("FROM")]
    assert "fd_yr1_ern_r" in head, "축 컬럼을 SELECT 에 덧붙여야 조립기가 값을 옮길 수 있다"
    assert "ORDER BY fd_yr1_ern_r DESC" in out


def test_축이_이미_맞으면_불개입():
    sql = "SELECT itm_no, fd_yr1_ern_r FROM public_funds ORDER BY fd_yr1_ern_r DESC LIMIT 3"
    assert ensure_fund_rank_axis(sql, Q) == (sql, False)


@pytest.mark.parametrize("q, want", [
    (Q, 3),
    ("순자산 큰 펀드 세 개 알려줘", 3),
    ("상위 10개 펀드", 10),
])
def test_질문이_명시한_개수로_LIMIT_을_맞춘다(q, want):
    sql = "SELECT itm_no, fd_yr1_ern_r FROM public_funds ORDER BY fd_yr1_ern_r DESC LIMIT 5"
    out, fixed = ensure_asked_topn(sql, q)
    assert fixed and out.endswith(f"LIMIT {want}")


@pytest.mark.parametrize("q", [
    "3년 수익률 높은 펀드 알려줘",          # 기간이지 개수가 아니다
    "호수가 2호인 펀드",                    # 호수
    "상위 5개 펀드 중 2개만",               # 개수 표현이 둘 — 어느 쪽인지 모른다
    "순자산 큰 펀드 알려줘",                # 개수 없음
])
def test_개수가_아니거나_모호하면_불개입(q):
    sql = "SELECT itm_no, fd_yr1_ern_r FROM public_funds ORDER BY fd_yr1_ern_r DESC LIMIT 5"
    assert ensure_asked_topn(sql, q)[1] is False


def test_단일_집계엔_불개입():
    sql = "SELECT COUNT(*) FROM public_funds ORDER BY 1 LIMIT 5"
    assert ensure_asked_topn(sql, "펀드 3개는 몇 개야")[1] is False
