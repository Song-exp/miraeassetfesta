# -*- coding: utf-8 -*-
"""2026-09-06 라운드 14 — 2차 재배포 재투입에서 SQL·결과는 정답인데 답변·순서에서 무너진 3건.

① "삼성전자 비중 5% 넘는 ETF 몇 개" — COUNT 212 를 받고 "정보를 포함하고 있지 않습니다": 집계 교정이 SELECT 머리의 /*g:ETFHOLD*/ 때문에 COUNT 를 못 봤다.
② "상장폐지 예정 ETF 있어?" — 71행을 받고 "정보를 찾을 수 없습니다 … 제공할 수 없습니다": 거절 문형이 정규식 밖.
③ "TR 지수 추종 ETF 몇 개" — 기초지수 확정식이 먼저 돌아 'Total Return' 을 지수식으로 바꿔 TR 확정식이 AND 로 덧붙여짐 → 207(정답 236).
"""
import pytest

from src.runtime import pipeline as P
from src.runtime.loader import connect_readonly


@pytest.fixture(scope="module")
def con():
    return connect_readonly()


def test_count_misrefusal_fixed_even_with_guard_comment_head():
    sql = ('SELECT /*g:ETFHOLD*/ COUNT(DISTINCT m.pd_itm_no) AS "ETF수" FROM domestic_etfs m LEFT JOIN ext_etf_holdings h '
           "ON h.etf_code = m.pd_itm_no WHERE m.pd_grp_no = 'ETF' AND /*g*/h.weight_pct > 5 LIMIT 1")
    rows = "ETF수\n212"
    a = "(국내 상장 ETF 기준, 기준일 2026-08-24) 조회된 결과는 삼성전자 비중이 5% 넘는 ETF의 개수에 대한 정보를 포함하고 있지 않습니다. 따라서 해당 질문에 대한 답변을 제공할 수 없습니다."
    out, fixed = P.ensure_positive_count_answered(a, sql, rows, 1, "삼성전자 비중이 5% 넘는 ETF 몇 개야?")
    assert fixed and "212" in out and "포함하고 있지 않" not in out


def test_rows_forced_on_new_refusal_phrasing():
    rows = "pd_nm | pd_abrv_nm | pd_lste_dt\n한국투자 ACE 적격TDF2030액티브증권상장지수투자신탁(주식혼합-재간접형) | ACE TDF2030액티브 적격 | 20260707\n미래에셋 TIGER 금속선물 특별자산상장지수투자신탁(금속-파생형) | TIGER 금속선물(H) | 20250804"
    a = "조회 결과에 상장폐지 예정인 ETF에 대한 정보를 찾을 수 없습니다. 따라서 답변을 제공할 수 없습니다."
    out, forced = P.ensure_rows_answered(a, rows, 71)
    assert forced and "ACE TDF2030" in out and "71행" in out
    # 부분 유보(값을 인용한 답)는 그대로 둔다
    partial = "TIGER 금속선물(H) 은 2025-08-04 폐지 예정입니다. 그 외는 확인할 수 없습니다."
    assert not P.ensure_rows_answered(partial, rows, 2)[1]


def test_where_trailing_order_is_moved_to_order_by(con):
    hcx = ("SELECT pd_abrv_nm, pd_dvid_yield AS 연환산분배수익률pct FROM domestic_etfs "
           "WHERE (pd_abrv_nm LIKE '%전기%' OR ref_base_index LIKE '%Electricity%') AND pd_dvid_yield DESC LIMIT 5")
    out, fixed = P.repair_where_order(hcx)
    assert fixed and out.endswith("ORDER BY pd_dvid_yield DESC LIMIT 5") and " DESC LIMIT 5" in out
    assert "AND pd_dvid_yield DESC" not in out and P.validate_sql(out) is None
    rows = con.execute(out).fetchall()
    assert 1 <= len(rows) <= 5 and rows[0][1] >= rows[-1][1]
    # WHERE 만 있는 꼴도 — 절을 떼면 WHERE 자체가 사라지고 기본모수 가드가 뒤에서 채운다
    out2, fixed2 = P.repair_where_order("SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_dvid_yield DESC LIMIT 5")
    assert fixed2 and "WHERE" not in out2.upper() and "ORDER BY pd_dvid_yield DESC LIMIT 5" in out2
    # 정상 SQL 은 불개입
    ok = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_grp_no = 'ETF' ORDER BY pd_dvid_yield DESC LIMIT 5"
    assert P.repair_where_order(ok) == (ok, False)


def test_union_join_columns_qualified_per_branch(con):
    """C10 — UNION 둘째 가지의 itm_no 에 첫 가지 별칭 e. 가 붙어 실행 실패(2026-09-06 2차 재배포). 가지마다 자기 별칭으로."""
    from src.runtime.loader import load_context
    ctx = load_context()
    sql = ("SELECT '국내 ETF' AS 구분, COUNT(*) AS 개수 FROM domestic_etfs e LEFT JOIN ext_etf_holdings h ON h.etf_code = e.pd_itm_no "
           "WHERE h.constituent = '삼성전자' AND e.pd_grp_no = 'ETF' AND pd_sale_yn = 1 UNION ALL "
           "SELECT '공모펀드', COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || "
           "COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) "
           "FROM public_funds p LEFT JOIN ext_fund_holdings f ON f.grp = p.mtco_itm_no AND f.or_co = p.or_co_xtn_itt_cd "
           "WHERE f.holding_nm = '삼성전자' AND p.sale_yn = '판매중' AND p.prvo_pbff_desc = '공모' LIMIT 30")
    out, cols = P.qualify_join_columns(sql, ctx)
    assert "e.itm_no" not in out and "p.itm_no" in out, out
    rows = con.execute(out).fetchall()
    assert len(rows) == 2 and rows[0][1] == 239 and rows[1][1] > 0


def test_tr_guard_replaces_index_canon_marked_total_return(con):
    q = "TR 지수를 추종하는 ETF 몇 개야?"
    hcx = ("SELECT COUNT(*) FROM domestic_etfs WHERE ((' '||ref_base_index||' ') GLOB '* TR *' "
           "OR ref_base_index LIKE '%Total Return%') AND pd_grp_no = 'ETF' AND pd_sale_yn = 1 LIMIT 30")
    # 새 순서: TR 확정식 → 기초지수 확정식. 두 번째 가드가 'Total Return' 을 지수명으로 삼지 않아야 한다
    s1, tr_fixed = P.ensure_etf_tr_index(hcx, q)
    s2, _ = P.ensure_etf_index_canon(s1, q)
    assert tr_fixed and "TotalReturn" not in s2 and s2.count("GLOB '* TR *'") == 1
    assert con.execute(s2.replace("/*g*/", "")).fetchone()[0] == 236
    # 옛 순서(기초지수 확정식이 먼저)로 표식이 붙은 절도 TR 확정식이 바꾼다
    s3, _ = P.ensure_etf_index_canon(hcx, q)
    s4, fixed = P.ensure_etf_tr_index(s3, q)
    assert fixed and con.execute(s4.replace("/*g*/", "")).fetchone()[0] == 236
