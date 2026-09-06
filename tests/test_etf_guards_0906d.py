# -*- coding: utf-8 -*-
"""2026-09-06 라운드 13 — 재배포 서버 재투입(A1~A19)에서 나온 결함 4건의 회귀 고정.

A8  "순자산 1조원 넘는 국내 ETF 몇 개야?" — HCX 가 `du_last_aum >= 10000000000`(100억)을 냈고 가드는 컬럼이 있다는 이유로 불개입 → 989(정답 91).
A9  "2026년에 상장한 ETF 알려줘" — 범위식은 맞았지만 모수가 없어 ETN 이 섞임(176행 · 정답 ETF 124).
A10 "TR 지수를 추종하는 ETF 몇 개야?" — `GLOB '*TR*'` 부분일치 212(TRF·STRIP 오탐) · 옛 규칙식은 괄호·철자 표기 42건 누락 → 정본 236.
A16 "상장폐지 예정인 ETF 있어?" — 기본모수 가드가 HCX 의 `pd_lste_dt <> 99991231` 을 날조 술어로 지움(가드 훼손 7회) → ETF 전체 30행.
정답은 전부 로컬 DB(스냅샷 2026-08-22) 실측.
"""
import pytest

from src.runtime import pipeline as P
from src.runtime.loader import connect_readonly


@pytest.fixture(scope="module")
def con():
    return connect_readonly()


def _count(con, sql):
    return con.execute(sql.replace("/*g*/", "")).fetchone()[0]


# ── A8 순자산 임계 — 있으면 확인하고 아니면 교체 ─────────────────────────────────────────────

def test_aum_threshold_wrong_scale_is_replaced(con):
    q = "순자산 1조원 넘는 국내 ETF 몇 개야?"
    sql = "SELECT COUNT(*) FROM domestic_etfs WHERE du_last_aum >= 10000000000 AND pd_grp_no = 'ETF' AND pd_sale_yn = 1 LIMIT 30"
    out, fixed = P.ensure_etf_aum_threshold(sql, q)
    assert fixed and "du_last_aum > 1000000000000" in out and "10000000000 " not in out
    assert _count(con, out) == 91


def test_aum_threshold_correct_is_untouched_and_sentinel_kept():
    q = "순자산 5천억 이상 ETF 몇 개?"
    ok = "SELECT COUNT(*) FROM domestic_etfs WHERE du_last_aum >= 500000000000 AND pd_grp_no = 'ETF' LIMIT 30"
    assert P.ensure_etf_aum_threshold(ok, q) == (ok, False)
    # `> 0` 은 결측 제외식 — 임계로 오인하지 않고 임계를 덧붙인다
    sent = "SELECT pd_abrv_nm FROM domestic_etfs WHERE du_last_aum > 0 AND pd_grp_no = 'ETF' ORDER BY du_last_aum DESC LIMIT 30"
    out, fixed = P.ensure_etf_aum_threshold(sent, q)
    assert fixed and "du_last_aum > 0" in out and "du_last_aum >= 500000000000" in out


# ── A9 상장연도 확정식 — 모수를 함께 세운다 ───────────────────────────────────────────────────

def test_listing_year_injects_base_population(con):
    q = "2026년에 상장한 ETF 알려줘"
    out, fixed = P.ensure_etf_listing_year("SELECT pd_nm, pd_abrv_nm FROM domestic_etfs WHERE 20261231 LIMIT 30", q)
    assert fixed and "pd_lstg_dt BETWEEN 20260101 AND 20261231" in out
    assert "pd_grp_no = 'ETF'" in out and "pd_sale_yn = 1" in out
    assert _count(con, out.replace("SELECT pd_nm, pd_abrv_nm", "SELECT COUNT(*)").replace("LIMIT 30", "")) == 124


def test_listing_year_etn_question_keeps_group_open():
    out, fixed = P.ensure_etf_listing_year("SELECT pd_nm FROM domestic_etfs LIMIT 30", "2026년에 상장한 ETN 알려줘")
    assert fixed and "pd_grp_no" not in out and "pd_sale_yn = 1" in out


# ── A10 TR·PR 지수 확정식 ───────────────────────────────────────────────────────────────────

def test_tr_partial_glob_is_replaced_by_canon(con):
    q = "TR 지수를 추종하는 ETF 몇 개야?"
    sql = "SELECT COUNT(*) FROM domestic_etfs WHERE ref_base_index GLOB '*TR*' AND pd_grp_no = 'ETF' AND pd_sale_yn = 1 LIMIT 30"
    out, fixed = P.ensure_etf_tr_index(sql, q)
    assert fixed and "GLOB '*TR*'" not in out and "GLOB '* TR *'" in out and "Total Return" in out
    assert P._GUARD_MARK in out
    assert _count(con, out) == 236
    # 판매중 조건이 없으면 전체 ETF 243
    assert _count(con, out.replace("AND pd_sale_yn = 1", "")) == 243


def test_tr_canon_survives_base_population_and_like_variant():
    q = "총수익 지수 추종 ETF 몇 개?"
    sql = "SELECT COUNT(*) FROM domestic_etfs WHERE ref_base_index LIKE '%TR%' LIMIT 30"
    out, _ = P.ensure_etf_tr_index(sql, q)
    out2, _ = P.ensure_etf_base_population(out, q)
    assert "Total Return" in out2 and "LIKE '%TR%'" not in out2, "표식 절은 날조 판별을 비켜 가야 한다"
    assert "pd_grp_no = 'ETF'" in out2


def test_tr_guard_silent_without_intent_and_pr_variant():
    assert P.ensure_etf_tr_index("SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' LIMIT 30", "삼성전자 담은 ETF 몇 개야?")[1] is False
    assert P.ensure_etf_tr_index("SELECT COUNT(*) FROM overseas_etfs WHERE pd_grp_no = 'ETF' LIMIT 30", "TR 지수 해외 ETF")[1] is False
    out, fixed = P.ensure_etf_tr_index("SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' LIMIT 30", "PR 지수 추종 ETF 몇 개?")
    assert fixed and "GLOB '* PR *'" in out and "Price Return" in out


# ── A16 상장폐지 확정식 — 기본모수 가드가 지우지 못하게 표식으로 ────────────────────────────────

def test_delist_condition_survives_base_population(con):
    q = "상장폐지 예정인 ETF 있어?"
    hcx = "SELECT pd_itm_no, pd_nm FROM domestic_etfs WHERE pd_lste_dt <> 99991231 AND pd_grp_no = 'ETF' LIMIT 30"
    out, fixed = P.ensure_etf_delist(hcx, q)
    assert fixed and P._GUARD_MARK + "pd_lste_dt <> 99991231" in out
    out2, _ = P.ensure_etf_base_population(out, q)
    assert "pd_lste_dt <> 99991231" in out2 and "pd_sale_yn = 1" not in out2
    assert _count(con, out2.replace("SELECT pd_itm_no, pd_nm", "SELECT COUNT(*)").replace("LIMIT 30", "")) == 71


def test_delist_injects_when_missing_and_drops_sale_filter():
    q = "상폐 예정 ETF 몇 개야?"
    out, fixed = P.ensure_etf_delist("SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1 LIMIT 30", q)
    assert fixed and "pd_lste_dt <> 99991231" in out and "pd_sale_yn" not in out
    assert P.ensure_etf_delist("SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' LIMIT 30", "구매 가능한 ETF 몇 개야?")[1] is False
