# -*- coding: utf-8 -*-
"""2026-09-05 라운드 8 수리분 회귀 — 기초지수 확정식의 TR 오해 · 순자산 임계 축 · 상장연도 축 · 상수 WHERE 기각.

#36 은 **가드가 정답을 지운** 세 번째 사고다(GROUP BY 절반 수리 · 백분율 반올림 · 이번 TR).
첫 테스트가 그 정답 케이스를 박아 두고, 동시에 진짜 지수명(KOSPI200)은 여전히 확정식으로 바뀌는지 같이 본다.
"""
from src.runtime import pipeline as P


# ── #36 TR 지수 — 'TR' 은 수익유형 접미다. 지수명으로 삼아 GLOB 'TR' 로 바꾸면 0건 ──────

def test_index_canon_leaves_return_type_suffix_alone():
    sql = ("SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1 "
           "AND (' '||ref_base_index||' ') GLOB '* TR *'")
    out, changed = P.ensure_etf_index_canon(sql)
    assert not changed, out
    like = "SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND ref_base_index LIKE '%TR%'"
    out2, changed2 = P.ensure_etf_index_canon(like)
    assert not changed2 and "GLOB 'TR'" not in out2, out2


def test_index_canon_still_canonicalizes_real_index_names():
    sql = "SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND ref_base_index LIKE '%KOSPI 200%'"
    out, changed = P.ensure_etf_index_canon(sql)
    assert changed and "GLOB 'KOSPI200'" in out, out


# ── #37 순자산 1조 — 금액 임계가 SQL 에서 통째로 사라진 네 번째 축 누락 ──────────────

def test_aum_threshold_injected_for_over_one_trillion():
    sql = "SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1 LIMIT 30"
    out, fixed = P.ensure_etf_aum_threshold(sql, "순자산 1조원 넘는 국내 ETF 몇 개야?")
    assert fixed and "du_last_aum > 1000000000000" in out, out


def test_aum_threshold_units_directions_and_noninterference():
    sql = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_grp_no = 'ETF' LIMIT 30"
    out, _ = P.ensure_etf_aum_threshold(sql, "순자산 5천억 이상인 ETF")
    assert "du_last_aum >= 500000000000" in out
    out, _ = P.ensure_etf_aum_threshold(sql, "AUM 100억 미만 ETF 몇 개")
    assert "du_last_aum < 10000000000" in out
    # 이미 있으면 불개입 · 임계 없는 순자산 질문(정렬만)은 불개입 · 해외는 불개입(통화 미확정)
    has = "SELECT COUNT(*) FROM domestic_etfs WHERE du_last_aum >= 1e12 AND pd_grp_no = 'ETF'"
    assert not P.ensure_etf_aum_threshold(has, "순자산 1조원 넘는 ETF")[1]
    assert not P.ensure_etf_aum_threshold(sql, "순자산 가장 큰 ETF 5개")[1]
    ovs = "SELECT COUNT(*) FROM overseas_etfs WHERE pd_grp_no = 'ETF'"
    assert not P.ensure_etf_aum_threshold(ovs, "순자산 1조원 넘는 해외 ETF")[1]


# ── #40 2026년 상장 — `WHERE 20261231 LIMIT 30` : 컬럼 없는 상수는 항상 참 ───────────

def test_listing_year_replaces_bare_date_constant():
    sql = "SELECT pd_nm, pd_abrv_nm, pd_lstg_dt FROM domestic_etfs WHERE 20261231 LIMIT 30"
    # (SELECT 에 pd_lstg_dt 가 있어도 WHERE 에 없으면 축은 비어 있다 — 그 구분은 WHERE 본문으로 본다)
    sql = "SELECT pd_nm, pd_abrv_nm FROM domestic_etfs WHERE 20261231 LIMIT 30"
    out, fixed = P.ensure_etf_listing_year(sql, "2026년에 상장한 ETF 알려줘")
    assert fixed
    assert "WHERE pd_lstg_dt BETWEEN 20260101 AND 20261231" in out, out
    assert "WHERE 20261231" not in out
    # 2026-09-06 A9 재배포 실측 뒤 — 확정식이 모수(ETF·판매중)도 함께 세운다(목록 질의는 기본모수 가드가 비켜 가서 ETN 이 섞였다)
    assert "pd_grp_no = 'ETF'" in out and "pd_sale_yn = 1" in out and out.rstrip().endswith("LIMIT 30")


def test_listing_year_appends_and_respects_direction_and_existing():
    sql = "SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1"
    out, fixed = P.ensure_etf_listing_year(sql, "2025년 이후 상장한 ETF 몇 개야")
    assert fixed and "pd_lstg_dt >= 20250101" in out, out
    out, fixed = P.ensure_etf_listing_year(sql, "올해 새로 나온 ETF 몇 개?")
    assert fixed and "pd_lstg_dt BETWEEN 20260101 AND 20261231" in out
    ovs = "SELECT COUNT(*) FROM overseas_etfs WHERE pd_grp_no = 'ETF'"
    assert P.ensure_etf_listing_year(ovs, "2024년 상장한 해외 ETF")[1], "해외에도 pd_lstg_dt 가 있다"
    has = "SELECT COUNT(*) FROM domestic_etfs WHERE pd_lstg_dt >= 20260101"
    assert not P.ensure_etf_listing_year(has, "2026년 상장 ETF")[1]
    assert not P.ensure_etf_listing_year(sql, "2026년 수익률 좋은 ETF")[1], "상장 낱말이 없으면 불개입"


def test_validate_sql_rejects_bare_constant_where():
    err = P.validate_sql("SELECT pd_nm FROM domestic_etfs WHERE 20261231 LIMIT 30")
    assert err and "상수 조건" in err, err
    err2 = P.validate_sql("SELECT pd_nm FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND 2026 LIMIT 30")
    assert err2 and "상수 조건" in err2, err2
    err3 = P.validate_sql("SELECT pd_nm FROM domestic_etfs WHERE 'ETF' LIMIT 30")
    assert err3 and "상수 조건" in err3, err3


def test_validate_sql_keeps_between_and_normal_predicates():
    assert P.validate_sql("SELECT COUNT(*) FROM domestic_etfs WHERE pd_lstg_dt BETWEEN 20260101 AND 20261231 LIMIT 30") is None
    assert P.validate_sql("SELECT pd_nm FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND du_last_aum > 1000000000000 "
                          "ORDER BY du_last_aum DESC LIMIT 5") is None
    assert P.validate_sql("SELECT pd_nm FROM domestic_etfs WHERE (pd_risk_cd = 6 OR pd_risk_cd = 5) AND pd_sale_yn = 1 LIMIT 30") is None
