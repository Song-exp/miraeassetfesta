# -*- coding: utf-8 -*-
"""펀드 유형 축 판정은 WHERE 본문만 본다 — 2026-09-06 FV-3a 서버 실측.

편입 확정식 경로는 근거컬럼 보강이 SELECT 에 `MAX(zrin_btyp_nm) AS "유형"` 을 항상 싣는다. 종전 판정이 SQL 전체를
봐서 그 조회 컬럼을 축 조건으로 오인했고, WHERE 엔 축이 없으니 침묵했다 — "삼성전자가 편입된 국내 **주식형**
공모펀드" 가 주식형 조건 없이 516펀드(정답 305)로 나가고 1위가 채권혼합형이었다.
"""
import pytest

from src.runtime import pipeline as P
from src.runtime.loader import connect_readonly, db_path

needs_db = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

Q = "삼성전자가 편입된 국내 주식형 공모펀드를 알려줘"
HOLDINGS_SQL = (
    'SELECT MIN(itm_no) AS itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", '
    'MAX(fd_nast_suma) AS fd_nast_suma, MAX(zrin_fd_ivst_risk_grd_nm) AS "위험등급", '
    'MAX(zrin_btyp_nm) AS "유형", MAX(or_attr_desc) AS "약관분류" '
    "FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_ivst_rgn_desc = '국내' "
    "AND (printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || TRIM(mtco_itm_no)) IN "
    "(SELECT printf('%08d', CAST(h.or_co AS INTEGER)) || '/' || TRIM(h.grp) FROM ext_fund_holdings h "
    "WHERE UPPER(h.holding_nm) IN ('삼성전자')) "
    "GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), "
    "printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 "
    "THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) "
    "ORDER BY fd_nast_suma DESC LIMIT 30"
)


def test_select_only_axis_column_does_not_block_injection():
    out, ok = P.ensure_fund_type_axis(HOLDINGS_SQL, Q)
    assert ok, "SELECT 의 조회 컬럼은 WHERE 조건이 아니다 — 주입되어야 한다"
    assert "zrin_btyp_nm = '주식형'" in out, out


def test_where_axis_is_still_respected():
    sql = "SELECT itm_nm FROM public_funds WHERE sale_yn='판매중' AND zrin_btyp_nm = '주식형' LIMIT 5"
    assert P.ensure_fund_type_axis(sql, Q) == (sql, False), "이미 확정식이면 손대지 않는다"


def test_no_type_word_in_question_is_untouched():
    assert P.ensure_fund_type_axis(HOLDINGS_SQL, "삼성전자가 편입된 공모펀드 알려줘") == (HOLDINGS_SQL, False)


def test_idempotent():
    once, _ = P.ensure_fund_type_axis(HOLDINGS_SQL, Q)
    assert P.ensure_fund_type_axis(once, Q) == (once, False)


@needs_db
def test_rows_are_equity_funds_and_top_matches_db(con=None):
    out, _ = P.ensure_fund_type_axis(HOLDINGS_SQL, Q)
    rows = connect_readonly().execute(out).fetchall()
    assert rows[0][1].startswith("한국밸류10년투자연금"), rows[0][1]
    assert all(r[5] == "주식형" for r in rows), [r[5] for r in rows[:5]]
