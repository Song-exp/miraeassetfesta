# -*- coding: utf-8 -*-
"""2026-09-06 라운드 10 수리분 회귀 — 안 쓰는 외부표 조인 제거 가드의 맨 컬럼 참조 · 교차 힌트 '지분'.

#42 "미래에셋자산운용이 운영하는 etf중 가장 삼성전자지분이 많은건 뭐야 레버리지를 제외하고":
HCX 가 `LEFT JOIN ext_etf_holdings … SUM(weight_pct)` 를 냈는데 `drop_unused_ext_join` 이 한정자 없는 weight_pct 를
못 보고 JOIN 을 걷어내 실행 실패(no such column). 가드가 정답을 부순 네 번째 사고 — 정답 케이스를 박아 둔다.
"""
from src.runtime import gate as G
from src.runtime import guard as GD

SCHEMA = {
    "domestic_etfs": [("pd_nm", "상품명", "TEXT"), ("pd_abrv_nm", "약어명", "TEXT"), ("pd_itm_no", "상품번호", "TEXT"),
                      ("ref_fund_mgmt_co", "운용사", "TEXT"), ("pd_grp_no", "군", "TEXT"), ("du_last_aum", "AUM", "REAL")],
    "ext_etf_holdings": [("etf_code", "코드", "TEXT"), ("constituent", "종목", "TEXT"), ("weight_pct", "비중", "REAL")],
    "ext_fund_page": [("itm_no", "코드", "TEXT"), ("set_dt", "설정일", "TEXT")],
}

SQL42 = ("SELECT pd_nm, pd_abrv_nm, SUM(weight_pct) as weight_pct FROM domestic_etfs "
         "LEFT JOIN ext_etf_holdings ON ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no "
         "WHERE ref_fund_mgmt_co = 'Mirae Asset Global Investments Co Ltd' AND pd_grp_no = 'ETF' "
         "GROUP BY pd_nm, pd_abrv_nm ORDER BY weight_pct DESC LIMIT 1")


def test_unused_ext_join_guard_keeps_join_when_bare_column_is_used():
    out, dropped = GD.drop_unused_ext_join(SQL42, SCHEMA)
    assert dropped == [], dropped
    assert "LEFT JOIN ext_etf_holdings" in out
    # constituent 만 맨 이름으로 쓴 경우도 사용이다
    sql = ("SELECT pd_abrv_nm FROM domestic_etfs LEFT JOIN ext_etf_holdings h ON h.etf_code = domestic_etfs.pd_itm_no "
           "WHERE constituent = '삼성전자' LIMIT 5")
    assert GD.drop_unused_ext_join(sql, SCHEMA)[1] == []


def test_unused_ext_join_guard_still_drops_truly_unused_join():
    sql = ("SELECT pd_abrv_nm, du_last_aum FROM domestic_etfs LEFT JOIN ext_fund_page e ON e.itm_no = domestic_etfs.pd_itm_no "
           "WHERE pd_grp_no = 'ETF' ORDER BY du_last_aum DESC LIMIT 5")
    out, dropped = GD.drop_unused_ext_join(sql, SCHEMA)
    assert dropped == ["ext_fund_page"], dropped
    assert "ext_fund_page" not in out
    # 스키마를 안 주면 종전 동작(한정자 참조만 본다) — 옛 호출 호환
    assert GD.drop_unused_ext_join(sql)[1] == ["ext_fund_page"]


def test_safe_grade_guard_leaves_pension_safe_asset_alone():
    # #38 — 서버가 맞힌 유일한 문항(218). '안전자산' 은 위험등급이 아니라 연금 분류 값이다 — 가드가 6·5등급을 주입하면 111 로 깨진다
    from src.runtime import pipeline as P
    sql = ("SELECT COUNT(*) FROM domestic_etfs WHERE pd_pen_tr_yn = 'Y' AND pd_pen_risk_nm = '안전자산' "
           "AND pd_grp_no = 'ETF' AND pd_sale_yn = 1 LIMIT 30")
    out, fixed = P.ensure_etf_safe_grade(sql, "연금계좌에서 살 수 있는 안전자산 ETF 몇 개야?")
    assert not fixed and "pd_risk_nm" not in out
    # 진짜 '안전한 ETF' 질의에는 여전히 개입한다
    plain = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_grp_no = 'ETF' ORDER BY du_last_aum DESC LIMIT 5"
    assert P.ensure_etf_safe_grade(plain, "안전한 ETF 추천해줘")[1]


def test_cross_hint_covers_stake_phrasing():
    assert "지분" in G._CROSS_HINTS
    q = "미래에셋자산운용이 운영하는 etf중 가장 삼성전자지분이 많은건 뭐야 레버리지를 제외하고"
    assert G.is_cross_query(q, ["domestic_etfs", "overseas_etfs"])
