# -*- coding: utf-8 -*-
"""2026-09-05 라운드 7 수리분 회귀 — 백분율 가드 반올림 · 1행 거절 전사 · ETF 축 확정식 · 기간수익률 정렬.

#32 는 **가드가 정답을 지운** 사고다. 이 파일의 첫 테스트가 그 정답 케이스를 박아 둔다 —
가드는 정답을 건드리지 않는다는 것을 회귀로 보증한다.
"""
from src.runtime import pipeline as P


# ── #32 분배율 3개 — 결과 27.783191 · 답변 27.78% 는 같은 값이다 ──────────────

ROWS_DVID = ("pd_abrv_nm | pd_dvid_yield\n"
             "SOL 팔란티어커버드콜OTM채권혼합 | 27.783191\n"
             "PLUS 고배당주위클리커버드콜 | 24.721569\n"
             "ACE 미국빅테크7+데일리타겟커버드콜(합성) | 23.917625")


def test_percent_guard_keeps_rounded_values_from_rows():
    a = ("분배율이 가장 높은 ETF 3개입니다. 1. SOL 팔란티어커버드콜OTM채권혼합 27.78% "
         "2. PLUS 고배당주위클리커버드콜 24.72% 3. ACE 미국빅테크7+데일리타겟커버드콜(합성) 23.92%")
    out, dropped = P.strip_unsourced_percent(a, ROWS_DVID)
    assert dropped == [], dropped
    assert "27.78%" in out and "SOL 팔란티어" in out


def test_percent_guard_still_drops_self_arithmetic():
    rows = "종목 | 비중\nA | 24.95\nB | 15.9\nC | 7.96"
    a = "A 24.95%, B 15.9%, C 7.96% 입니다. 세 종목 합계는 약 48.81% 입니다."
    out, dropped = P.strip_unsourced_percent(a, rows)
    assert "48.81" in "".join(dropped)
    assert "48.81" not in out and "24.95%" in out


# ── #35 거래 활발 — 1행 받고 이름만 인용한 거절은 전사로 교체 ──────────────────

ROWS_VAL = "pd_abrv_nm | du_val_1d\nKODEX 200 | 3638952836947.0"


def test_rows_answered_forces_transcription_when_only_name_is_cited():
    a = ("조회 결과에는 KODEX 200 ETF의 거래량 정보만 포함되어 있으며, 전체적으로 거래량이 가장 활발한 ETF에 대한 "
         "정보는 제공되지 않습니다. 따라서 해당 질문에 대한 답변을 드릴 수 없습니다.")
    out, forced = P.ensure_rows_answered(a, ROWS_VAL, 1)
    assert forced, out
    assert "답변을 드릴 수 없" not in out and "KODEX 200" in out


def test_rows_answered_leaves_partial_answer_that_cites_a_number():
    a = "거래대금 기준 1위는 KODEX 200 (3638952836947.0원)입니다. 다른 축은 확인할 수 없습니다."
    out, forced = P.ensure_rows_answered(a, ROWS_VAL, 1)
    assert not forced


# ── #33 월배당 — 질문 축이 SQL 에서 통째로 사라진 세 번째 사례 ──────────────

def test_axis_filter_injects_monthly_distribution():
    sql = "SELECT COUNT(*) FROM domestic_etfs WHERE pd_sale_yn = 1 AND pd_grp_no = 'ETF' LIMIT 30"
    out, fixed = P.ensure_etf_axis_filter(sql, "월배당 ETF 몇 개야?")
    assert fixed and "pd_dvid_cycl = 'M'" in out


def test_axis_filter_pension_and_hedge_and_idempotent():
    sql = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_grp_no = 'ETF' ORDER BY du_last_aum DESC LIMIT 5"
    out, fixed = P.ensure_etf_axis_filter(sql, "연금계좌에서 살 수 있는 안전자산 ETF 몇 개야?")
    assert fixed and "pd_pen_tr_yn = 'Y'" in out
    out2, fixed2 = P.ensure_etf_axis_filter(sql, "환헤지된 미국 ETF 알려줘")
    assert fixed2 and "(H)" in out2
    # 이미 그 컬럼이 있으면 불개입
    has = "SELECT COUNT(*) FROM domestic_etfs WHERE pd_dvid_cycl = 'M' AND pd_grp_no = 'ETF' LIMIT 30"
    assert not P.ensure_etf_axis_filter(has, "월배당 ETF 몇 개야?")[1]
    # 해외에는 손대지 않는다(분배주기 컬럼이 없다 — absent 게이트 몫)
    ovs = "SELECT COUNT(*) FROM overseas_etfs WHERE pd_grp_no = 'ETF' LIMIT 30"
    assert not P.ensure_etf_axis_filter(ovs, "월배당 해외 ETF 몇 개야?")[1]


# ── #34 3개월 수익률 — ORDER BY 3 이 배수를 가리켰다 ──────────────────────────

def test_return_sort_fixes_ordinal_pointing_at_wrong_column():
    sql = ("SELECT pd_abrv_nm, du_er_3m, cu_lev_fector FROM domestic_etfs "
           "WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1 AND du_er_3m IS NOT NULL AND du_er_3m > -100 "
           "ORDER BY 3 DESC LIMIT 5")
    out, fixed = P.ensure_etf_return_sort(sql, "최근 3개월 수익률 좋은 국내 ETF 5개")
    assert fixed
    assert "ORDER BY du_er_3m DESC LIMIT 5" in out
    assert "ORDER BY 3" not in out


def test_return_sort_respects_correct_sort_and_direction_words():
    ok = ("SELECT pd_abrv_nm, du_er_3m, cu_lev_fector FROM domestic_etfs WHERE pd_grp_no = 'ETF' "
          "ORDER BY du_er_3m DESC LIMIT 5")
    assert not P.ensure_etf_return_sort(ok, "최근 3개월 수익률 좋은 국내 ETF 5개")[1]
    ok2 = ("SELECT pd_abrv_nm, du_er_3m, cu_lev_fector FROM domestic_etfs WHERE pd_grp_no = 'ETF' "
           "ORDER BY 2 DESC LIMIT 5")
    assert not P.ensure_etf_return_sort(ok2, "최근 3개월 수익률 좋은 국내 ETF 5개")[1], "서수 2 = du_er_3m 이면 그대로"
    bad_low = ("SELECT pd_abrv_nm, du_er_1y, cu_lev_fector FROM domestic_etfs WHERE pd_grp_no = 'ETF' "
               "ORDER BY cu_lev_fector LIMIT 5")
    out, fixed = P.ensure_etf_return_sort(bad_low, "1년 수익률 가장 낮은 ETF 5개")
    assert fixed and "ORDER BY du_er_1y ASC" in out
    # 기간이 둘이면 불개입(어느 컬럼인지 정할 수 없다)
    assert not P.ensure_etf_return_sort(bad_low, "1년 수익률과 3개월 수익률 비교")[1]
