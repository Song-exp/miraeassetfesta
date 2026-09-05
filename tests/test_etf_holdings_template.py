# -*- coding: utf-8 -*-
"""ETF 편입 확정식 — "○○를 담은/편입한 ETF" 질의를 코드가 SQL 로 세운다 (2026-09-06).

42문항에서 세 번 다른 자리에서 무너진 부류(#8 표기 창작 · #29 '비중' 미인식 · #42 조인 제거)다.
HCX 원문이 어떤 모양이든 종목 조건·조인·모수를 확정식이 정하고, 원문에서는 마스터 축 술어만 건진다.
실제 DB 로 결과까지 확인한다 — 정답은 로컬 실측(TIGER KTOP30 37.43% · 5% 초과 212 · 전체 239 · 에코프로 1위 KODEX 200).
"""
import pytest

from src.runtime import pipeline as P
from src.runtime.loader import load_context, connect_readonly


@pytest.fixture(scope="module")
def ctx():
    return load_context()


@pytest.fixture(scope="module")
def con():
    return connect_readonly()


def _run(ctx, con, q, tables, hcx_sql):
    hits, _ = P._ground(q, ctx, tables, True)
    out, note = P.rewrite_etf_holdings(hcx_sql, q, ctx, hits, tables)
    assert note, "확정식이 발동해야 한다"
    assert P.validate_sql(out) is None, out
    return out, con.execute(out).fetchall()


def test_42_samsung_stake_excluding_leverage(ctx, con):
    q = "미래에셋자산운용이 운영하는 etf중 가장 삼성전자지분이 많은건 뭐야 레버리지를 제외하고"
    hcx = ("SELECT pd_nm, pd_abrv_nm, SUM(weight_pct) as weight_pct FROM domestic_etfs "
           "LEFT JOIN ext_etf_holdings ON ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no "
           "WHERE ref_fund_mgmt_co = 'Mirae Asset Global Investments Co Ltd' GROUP BY pd_nm, pd_abrv_nm ORDER BY weight_pct DESC LIMIT 1")
    out, rows = _run(ctx, con, q, ["domestic_etfs", "overseas_etfs"], hcx)
    assert "m.ref_fund_mgmt_co = 'Mirae Asset Global Investments Co Ltd'" in out, "운용사 술어는 원문에서 건진다"
    assert "NOT (ABS(COALESCE(m.cu_lev_fector, 1)) > 1" in out, "'레버리지 제외' 는 부정 조건"
    assert rows[0][0] == "TIGER KTOP30" and abs(rows[0][1] - 37.43) < 0.01
    assert all("레버리지" not in r[0] for r in rows)


def test_29_weight_over_5pct_count(ctx, con):
    out, rows = _run(ctx, con, "삼성전자 비중이 5% 넘는 ETF 몇 개야?", ["domestic_etfs", "overseas_etfs"],
                     "SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no='ETF' LIMIT 30")
    assert "h.weight_pct > 5" in out and "COUNT(DISTINCT m.pd_itm_no)" in out
    assert rows == [(212,)]


def test_8_samsung_holding_count_no_invented_aliases(ctx, con):
    out, rows = _run(ctx, con, "삼성전자 담은 ETF 몇 개야?", ["domestic_etfs"], "SELECT COUNT(*) FROM domestic_etfs LIMIT 30")
    assert "'삼성전자우'" not in out and "'삼성전자'" in out, "종목 조건은 KG 접지 별칭만 — 표기를 지어내지 않는다"
    assert rows == [(239,)]


def test_31_ecopro_group_sorted_by_aum(ctx, con):
    out, rows = _run(ctx, con, "에코프로 자회사가 편입된 ETF 중 순자산 큰 상품 알려줘", ["domestic_etfs"],
                     "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_grp_no='ETF' ORDER BY du_last_aum DESC LIMIT 1")
    assert "'에코프로비엠'" in out and "'에코프로'" in out, "계열 관계 전개(후손 종목)가 조건에 들어간다"
    assert 'ORDER BY "순자산_원" DESC' in out
    assert rows[0][0] == "KODEX 200" and len(rows) == 30


def test_cambricon_prefers_domestic_and_drops_foreign_literal(ctx, con):
    # 국내·해외 둘로 라우팅되고 해외 표지가 없으면 국내 먼저 — FIN-19 gold 는 국내 RISE 차이나AI반도체TOP4Plus.
    # HCX 가 해외 표기 'China' 를 썼다면 값 색인 대조에서 그 절은 버린다(국내 값은 '중국').
    out, rows = _run(ctx, con, "캠브리콘이 편입된 중국 반도체 ETF 알려줘", ["domestic_etfs", "overseas_etfs"],
                     "SELECT pd_nm FROM overseas_etfs WHERE wu_inv_rgn = 'China' LIMIT 30")
    assert "FROM domestic_etfs m JOIN ext_etf_holdings h" in out
    assert "'China'" not in out
    names = [r[0] for r in rows]
    assert any("차이나AI반도체" in n for n in names), names
    # 해외라고 말하면 해외 편입표로
    out2, rows2 = _run(ctx, con, "캠브리콘이 편입된 해외 ETF 알려줘", ["overseas_etfs"], "SELECT pd_nm FROM overseas_etfs LIMIT 30")
    assert "ext_ovs_etf_holdings" in out2 and len(rows2) >= 10


def test_noninterference(ctx):
    hits, _ = P._ground("삼성전자 담은 펀드 알려줘", ctx, ["public_funds"], True)
    sql = "SELECT itm_nm FROM public_funds LIMIT 30"
    assert P.rewrite_etf_holdings(sql, "삼성전자 담은 펀드 알려줘", ctx, hits, ["public_funds"]) == (sql, None), "펀드 라우팅은 형의 확정식 몫"
    hits2, _ = P._ground("KODEX 200 총보수 알려줘", ctx, ["domestic_etfs"], True)
    sql2 = "SELECT cu_charge_rt FROM domestic_etfs WHERE TRIM(pd_abrv_nm) = 'KODEX 200' LIMIT 1"
    assert P.rewrite_etf_holdings(sql2, "KODEX 200 총보수 알려줘", ctx, hits2, ["domestic_etfs"]) == (sql2, None), "편입 어휘가 없으면 불개입"
    marked = "SELECT /*g:ETFHOLD*/ COUNT(DISTINCT m.pd_itm_no) FROM domestic_etfs m JOIN ext_etf_holdings h ON h.etf_code = m.pd_itm_no LIMIT 1"
    assert P.rewrite_etf_holdings(marked, "삼성전자 담은 ETF 몇 개야?", ctx, [], ["domestic_etfs"]) == (marked, None), "멱등"


def test_end_to_end_42_through_pipeline(ctx):
    class Stub:
        def plan_sql(self, q, g):
            return ("SELECT pd_nm, pd_abrv_nm, SUM(weight_pct) as weight_pct FROM domestic_etfs LEFT JOIN ext_etf_holdings "
                    "ON ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no WHERE ref_fund_mgmt_co = 'Mirae Asset Global Investments Co Ltd' "
                    "GROUP BY pd_nm, pd_abrv_nm ORDER BY weight_pct DESC LIMIT 1")
        def compose_answer(self, q, rows, answer_rules=""):
            self.rows = rows
            return "TIGER KTOP30 입니다."
    s = Stub()
    r = P.answer_question("t42", "미래에셋자산운용이 운영하는 etf중 가장 삼성전자지분이 많은건 뭐야 레버리지를 제외하고", planner=s, ctx=ctx)
    assert "ETF 편입 확정식" in r.think_trace and "[Execute] 3행" in r.think_trace, r.think_trace
    assert "TIGER KTOP30 | 37.43" in s.rows
