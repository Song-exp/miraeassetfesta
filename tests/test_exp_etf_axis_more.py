# -*- coding: utf-8 -*-
"""ETF 축 확정식 확장 — 인버스(부정 포함)·배수·추적오차 0 제외 (2026-09-06 재생 E25·E5·E7).

규칙 문서(📄)에만 있어 확률적으로 지켜지던 세 축을 코드 가드(🔧)로. 정답 케이스(조건이 이미 있는 SQL)는 불변.
"""
import pytest

from src.runtime import pipeline as P
from src.runtime.loader import connect_readonly, db_path

DOM = "SELECT pd_abrv_nm, cu_lev_fector FROM domestic_etfs WHERE cu_lev_fector > 1 LIMIT 30"


def test_inverse_negation_domestic():
    out, ok = P.ensure_etf_axis_filter(DOM, "레버리지 ETF 중에서 인버스는 빼고 알려줘")
    assert ok and "NOT (pd_abrv_nm LIKE '%인버스%' OR pd_nm LIKE '%인버스%')" in out, out
    assert "ABS(COALESCE" not in out, "레버리지 조건은 이미 있으니 다시 넣지 않는다"


def test_inverse_positive_and_overseas_column():
    out, ok = P.ensure_etf_axis_filter("SELECT pd_nm FROM overseas_etfs WHERE pd_grp_no = 'ETF' LIMIT 30", "해외 인버스 ETF 알려줘")
    assert ok and "cu_inverse_short_yn = 'Y'" in out, out
    out, ok = P.ensure_etf_axis_filter("SELECT pd_nm FROM domestic_etfs LIMIT 30", "인버스 ETF 몇 개야?")
    assert ok and "(pd_abrv_nm LIKE '%인버스%' OR pd_nm LIKE '%인버스%')" in out and "NOT" not in out


def test_multiplier_from_question():
    out, ok = P.ensure_etf_axis_filter(
        "SELECT pd_nm FROM overseas_etfs WHERE wu_inv_rgn = 'United States of America' LIMIT 30", "미국 3배 레버리지 ETF 뭐 있어?")
    assert ok and "ABS(cu_lev_fector) = 3" in out, out
    assert "> 1" not in out, "배수를 물었으면 '레버리지 있음' 조건은 중복이라 넣지 않는다"


def test_leverage_exclusion_and_no_double_injection():
    out, ok = P.ensure_etf_axis_filter("SELECT pd_nm FROM domestic_etfs LIMIT 30", "레버리지 빼고 반도체 ETF 알려줘")
    assert ok and "NOT (ABS(COALESCE(cu_lev_fector, 1)) > 1)" in out, out
    assert P.ensure_etf_axis_filter(out, "레버리지 빼고 반도체 ETF 알려줘") == (out, False)


def test_tracking_error_zero_excluded_only_when_column_used():
    sql = "SELECT pd_abrv_nm, du_chas_errt FROM domestic_etfs WHERE pd_grp_no = 'ETF' ORDER BY du_chas_errt ASC LIMIT 30"
    out, ok = P.ensure_etf_axis_filter(sql, "추적오차 작은 ETF 알려줘")
    assert ok and "du_chas_errt > 0" in out, out
    plain = "SELECT pd_abrv_nm FROM domestic_etfs LIMIT 30"
    assert P.ensure_etf_axis_filter(plain, "추적오차 작은 ETF 알려줘") == (plain, False)


def test_join_statement_left_to_holdings_template():
    j = ("SELECT m.pd_abrv_nm FROM domestic_etfs m JOIN ext_etf_holdings h ON h.etf_code = m.pd_itm_no "
         "WHERE h.stock_name = '삼성전자' LIMIT 30")
    assert P.ensure_etf_axis_filter(j, "삼성전자 담은 ETF 중 인버스 빼고") == (j, False)


def test_no_false_multiplier_on_dividend_words():
    plain = "SELECT pd_abrv_nm FROM domestic_etfs LIMIT 30"
    out, ok = P.ensure_etf_axis_filter(plain, "월배당 ETF 중 2배당 하는 것")
    assert "ABS(cu_lev_fector)" not in out


@pytest.mark.skipif(not db_path().exists(), reason="DB 없음")
def test_counts_against_db():
    con = connect_readonly()
    out, _ = P.ensure_etf_axis_filter("SELECT COUNT(*) FROM domestic_etfs WHERE cu_lev_fector > 1 AND pd_grp_no = 'ETF' AND pd_sale_yn = 1 LIMIT 30",
                                      "레버리지 ETF 중에서 인버스는 빼고 몇 개야?")
    assert con.execute(out).fetchall() == [(62,)], out
    out, _ = P.ensure_etf_axis_filter("SELECT COUNT(*) FROM overseas_etfs WHERE wu_inv_rgn = 'United States of America' AND pd_grp_no = 'ETF' LIMIT 30",
                                      "미국 3배 레버리지 ETF 몇 개야?")
    assert con.execute(out).fetchall() == [(57,)], out
