# -*- coding: utf-8 -*-
"""6차 회귀 셋 — HCX 가 컬럼을 잘못 고른 한 부류.

KG-005: 운용사 코드를 mtco_itm_no 에 → 접지가 말한 or_co_xtn_itt_cd 로.
FND-014: '위험등급 정보가 없는' 을 fd_yr1_ern_r IS NULL 로 → 위험등급명 컬럼으로.
FND-005: 보수 합 0(미수록 역외) 이 하위 랭킹에 → 모수에서 뺀다. 덤: MIN(MIN()) 이중 감싸기.
"""

import pytest

from src.runtime.loader import load_context
from src.runtime.pipeline import (_inside_aggregate, ensure_absent_attr_column, ensure_fee_rank_nonzero,
                                  ensure_grounded_org_code_column)


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def test_운용사_코드가_다른_컬럼에_걸리면_접지_컬럼으로(ctx):
    sql = "SELECT COUNT(*) FROM public_funds WHERE mtco_itm_no = '00040010' AND sale_yn = '판매중' LIMIT 30"
    out, fixes = ensure_grounded_org_code_column(sql, ctx)
    assert "or_co_xtn_itt_cd = '00040010'" in out and "mtco_itm_no" not in out
    assert fixes == ["mtco_itm_no→or_co_xtn_itt_cd('00040010')"]


def test_수탁사_코드는_수탁_컬럼으로(ctx):
    sql = "SELECT COUNT(*) FROM public_funds WHERE itm_no = '00020004' LIMIT 30"
    out, _ = ensure_grounded_org_code_column(sql, ctx)
    assert "trusc_xtn_itt_cd = '00020004'" in out


def test_역할_컬럼에_이미_있거나_KG_에_없는_코드는_불개입(ctx):
    for sql in ("SELECT COUNT(*) FROM public_funds WHERE or_co_xtn_itt_cd = '00040010' LIMIT 30",
                "SELECT COUNT(*) FROM public_funds WHERE mtco_itm_no = '99999999' LIMIT 30"):
        assert ensure_grounded_org_code_column(sql, ctx) == (sql, [])


def test_부재_속성_컬럼을_질문의_속성으로(ctx):
    sql = ("SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' "
           "AND (prvo_pbff_desc = '공모' AND (fd_yr1_ern_r IS NULL OR fd_yr1_ern_r = -100)) LIMIT 30")
    out, was = ensure_absent_attr_column(sql, "위험등급 정보가 없는 공모펀드는 몇 개야?")
    assert was == "fd_yr1_ern_r"
    assert "zrin_fd_ivst_risk_grd_nm IS NULL" in out and "fd_yr1_ern_r" not in out


def test_속성을_이름_부르지_않았거나_이미_맞으면_불개입(ctx):
    sql = "SELECT COUNT(*) FROM public_funds WHERE zrin_fd_ivst_risk_grd_nm IS NULL LIMIT 30"
    assert ensure_absent_attr_column(sql, "위험등급 정보가 없는 공모펀드는 몇 개야?")[1] is None
    sql2 = "SELECT COUNT(*) FROM public_funds WHERE fd_yr1_ern_r IS NULL LIMIT 30"
    assert ensure_absent_attr_column(sql2, "1년 수익률이 없는 펀드는 몇 개야?")[1] is None


FEE = "or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r"


def test_보수_축_랭킹은_보수_합_0_을_뺀다(ctx):
    sql = (f"SELECT itm_no, MIN(ROUND(({FEE})/10.0, 4)) AS \"총보수_퍼센트\" FROM public_funds "
           f"WHERE sale_yn = '판매중' AND ({FEE}) IS NOT NULL GROUP BY itm_no ORDER BY 2 ASC LIMIT 5")
    out, fixed = ensure_fee_rank_nonzero(sql)
    assert fixed and f"({FEE}) > 0" in out
    assert ensure_fee_rank_nonzero(out) == (out, False)          # 멱등


def test_보수_축이_아니면_불개입(ctx):
    sql = "SELECT itm_no, fd_nast_suma FROM public_funds ORDER BY fd_nast_suma DESC LIMIT 5"
    assert ensure_fee_rank_nonzero(sql) == (sql, False)


def test_두_겹_괄호_안의_집계도_집계로_본다():
    head = f"SELECT itm_no, MIN(ROUND(({FEE})/10.0, 4)) AS x"
    assert _inside_aggregate(head, "or_co_rwrd_r")
    assert not _inside_aggregate("SELECT itm_no, or_co_rwrd_r", "or_co_rwrd_r")
