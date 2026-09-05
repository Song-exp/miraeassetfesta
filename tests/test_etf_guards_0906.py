# -*- coding: utf-8 -*-
"""2026-09-06 라운드 9 수리분 회귀 — 창작 임계 제거 · 기초지수 확정식의 지수 의도 판정.

#41 "전기테마 etf중에 고배당은뭐있어" — HCX 가 '고배당' 을 `pd_dvid_yield > 5` 로 옮겨 0건.
정도 형용사는 임계가 아니라 정렬이다. 가드는 규칙이 준 `> 0`·`> -100` 과 질문이 숫자를 준 경우는 건드리지 않는다.
"""
from src.runtime import pipeline as P

Q41 = "전기테마 etf중에 고배당은뭐있어"
SQL41 = ("SELECT pd_abrv_nm, pd_nm, pd_dvid_yield AS 연환산분배수익률pct FROM domestic_etfs "
         "WHERE replace(pd_nm,' ','') LIKE '%전기%' AND pd_dvid_yield > 5 AND pd_grp_no = 'ETF' AND pd_sale_yn = 1 "
         "ORDER BY 3 DESC LIMIT 5")


def test_invented_threshold_is_dropped_and_sort_kept():
    out, fixed = P.ensure_etf_no_invented_threshold(SQL41, Q41)
    assert fixed
    assert "pd_dvid_yield > 5" not in out
    assert "LIKE '%전기%'" in out and "pd_grp_no = 'ETF'" in out, "다른 절은 보존"
    assert "ORDER BY 3 DESC LIMIT 5" in out, "이미 있는 정렬·LIMIT 은 그대로"
    assert "pd_dvid_yield AS" in out, "SELECT 에 이미 있으면 다시 더하지 않는다"


def test_invented_threshold_adds_sort_and_select_when_missing():
    sql = ("SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND cu_charge_rt < 0.2 LIMIT 5")
    out, fixed = P.ensure_etf_no_invented_threshold(sql, "보수 저렴한 ETF 알려줘")
    assert fixed
    assert "cu_charge_rt < 0.2" not in out
    assert "ORDER BY cu_charge_rt ASC LIMIT 5" in out, out
    assert out.split("FROM")[0].count("cu_charge_rt") == 1, "답변이 값을 말할 수 있게 SELECT 에 병기"


def test_invented_threshold_respects_numbers_and_sanctioned_sentinels():
    # 질문이 숫자를 줬으면 임계는 사용자 의도다
    assert not P.ensure_etf_no_invented_threshold(SQL41, "전기 테마 ETF 중 분배율 5% 넘는 것")[1]
    # 규칙이 준 미입력·센티넬 제외식은 임계가 아니다
    ok = ("SELECT pd_abrv_nm, du_er_3m FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND du_er_3m > -100 "
          "AND cu_charge_rt > 0 ORDER BY du_er_3m DESC LIMIT 5")
    assert not P.ensure_etf_no_invented_threshold(ok, "최근 석 달 수익률 좋은 ETF")[1]
    # COUNT 질의는 절만 빼고 정렬을 더하지 않는다
    cnt = "SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND pd_dvid_yield > 3 LIMIT 30"
    out, fixed = P.ensure_etf_no_invented_threshold(cnt, "고배당 ETF 몇 개야")
    assert fixed and "ORDER BY" not in out and "pd_dvid_yield > 3" not in out, out
    # 단일 절이 임계뿐이면 WHERE 자체를 뺀다 — 문장이 깨지지 않아야 한다
    only = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_dvid_yield > 4 LIMIT 5"
    out, fixed = P.ensure_etf_no_invented_threshold(only, "고배당 ETF")
    assert fixed and "WHERE" not in out.upper(), out
    assert P.validate_sql(out) is None, out


def test_index_canon_needs_index_intent_in_question():
    theme = ("SELECT pd_abrv_nm FROM domestic_etfs WHERE (replace(pd_nm,' ','') LIKE '%전기%' "
             "OR replace(ref_base_index,' ','') LIKE '%Electric%') AND pd_grp_no = 'ETF' LIMIT 5")
    assert not P.ensure_etf_index_canon(theme, Q41)[1], "테마 낱말을 지수명으로 삼지 않는다"
    idx = "SELECT COUNT(*) FROM domestic_etfs WHERE ref_base_index LIKE '%S&P 500%' LIMIT 30"
    out, changed = P.ensure_etf_index_canon(idx, "S&P500 추종 ETF 몇 개야")
    assert changed and "GLOB 'S&P500'" in out
    assert P.ensure_etf_index_canon(idx)[1], "question 을 안 준 옛 호출은 종전대로 개입(회귀 호환)"
