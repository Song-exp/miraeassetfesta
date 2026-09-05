# -*- coding: utf-8 -*-
"""20R — 어려운 난이도 2문항 재점검 (2026-09-05 · 사고 #69·#70·#71).

① "한국전력공사 채권 중에 만기가 제일 긴 걸 사면 뭐가 위험해?" — 질문에 시점 낱말이 없는데 HCX 가 부질의에
   `mat_dt <= 20291231` 을 붙여 1013(2029-12-30) 오답. 실제 최장 1184(2052-04-21). → strip_unasked_maturity_cap
② "SK그룹 계열사가 발행한 채권 중에 발행잔액이 큰 3개랑 그 위험요인 알려줘" —
   `pd_pbcm LIKE '%SK%'` 가 '에스케이…' 16곳을 놓쳐 모수 205 vs 307 · 1위 에스케이하이닉스224-2 누락 → expand_issuer_acronym_prefix
   ORDER BY MAX(bd_tisu_a)(총발행액) 로 발행잔액(isu_bal_amt) 축을 바꿈 → ensure_sort_axis 혼동쌍 표
과적합 점검: 세 가드 모두 이 두 문항의 낱말이 아니라 부류(시점 낱말 부재 · 로마자 약칭 · 혼동쌍 축)로 발동하고,
정당한 상한('3년 안에'·'10년 만기'·'2028년까지')과 다른 축(만기 정렬)은 손대지 않는다.
"""
import sqlite3

import pytest

from src.runtime.loader import db_path
from src.runtime.pipeline import (
    _fmt_won, ensure_sort_axis, expand_issuer_acronym_prefix, strip_unasked_maturity_cap,
)

Q1 = "한국전력공사 채권 중에 만기가 제일 긴 걸 사면 뭐가 위험해?"
SQL1 = ("SELECT pd_nm, pd_risk_gcd, pd_risk_nm, mat_dt, remaining_days FROM domestic_bonds "
        "WHERE TRIM(pd_pbcm) = '한국전력공사(주)' AND mat_dt IS NOT NULL AND remaining_days = "
        "(SELECT MAX(remaining_days) FROM domestic_bonds WHERE TRIM(pd_pbcm) = '한국전력공사(주)' "
        "AND mat_dt >= 20260824 AND mat_dt <= 20291231) ORDER BY mat_dt DESC LIMIT 1")
Q2 = "SK그룹 계열사가 발행한 채권 중에 발행잔액이 큰 3개랑 그 위험요인 알려줘"
SQL2 = ("SELECT pd_nm, pd_pbcm, MAX(bd_tisu_a) AS bd_tisu_a , pd_risk_gcd, pd_risk_nm FROM domestic_bonds "
        "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND (pd_pbcm LIKE '%SK%' AND bd_tisu_a IS NOT NULL) "
        "GROUP BY pd_no ORDER BY MAX(bd_tisu_a) DESC LIMIT 3")


# ── ① 무근거 만기 상한 제거 ──────────────────────────────────────────────────────────
def test_cap_in_subquery_is_stripped_when_question_has_no_time_words():
    fixed, changed = strip_unasked_maturity_cap(SQL1, Q1)
    assert changed
    assert "20291231" not in fixed
    assert "mat_dt >= 20260824" in fixed                      # 부질의의 구매가능 하한은 남는다
    assert fixed.count("AND") == SQL1.count("AND") - 1        # 상한 절과 그 앞 AND 만 빠졌다


@pytest.mark.parametrize("q, sql", [
    ("3년 안에 만기되는 채권 알려줘", "SELECT pd_nm FROM domestic_bonds WHERE mat_dt >= 20260824 AND mat_dt <= 20290824 LIMIT 30"),
    ("10년 만기 채권 중 수익률 높은 것", "SELECT pd_nm FROM domestic_bonds WHERE mat_dt BETWEEN 20360101 AND 20361231 LIMIT 30"),
    ("2028년까지 만기인 채권", "SELECT pd_nm FROM domestic_bonds WHERE mat_dt >= 20260824 AND mat_dt <= 20281231 LIMIT 30"),
    ("1년만 굴릴 건데 어떤 채권 사면 돼?", "SELECT pd_nm FROM domestic_bonds WHERE mat_dt >= 20260824 AND mat_dt <= 20270824 LIMIT 30"),
    ("내년에 만기되는 회사채", "SELECT pd_nm FROM domestic_bonds WHERE mat_dt BETWEEN 20270101 AND 20271231 LIMIT 30"),
    ("삼년 이내 만기 채권", "SELECT pd_nm FROM domestic_bonds WHERE mat_dt <= 20290824 LIMIT 30"),
    ("단기 채권 추천해줘", "SELECT pd_nm FROM domestic_bonds WHERE mat_dt <= 20270824 LIMIT 30"),
    ("만기 지난 채권은 어떻게 됐어", "SELECT pd_nm FROM domestic_bonds WHERE mat_dt <= 20260823 LIMIT 30"),
])
def test_cap_kept_when_question_defines_a_window(q, sql):
    assert strip_unasked_maturity_cap(sql, q) == (sql, False)


def test_cap_stripped_for_shortest_maturity_sort_and_floor_kept():
    sql = "SELECT pd_nm, mat_dt FROM domestic_bonds WHERE mat_dt >= 20260824 AND mat_dt <= 20271231 ORDER BY mat_dt ASC LIMIT 3"
    fixed, changed = strip_unasked_maturity_cap(sql, "만기 가장 짧은 채권 3개")
    assert changed and "20271231" not in fixed and "mat_dt >= 20260824" in fixed


def test_cap_alone_in_where_is_removed_and_floor_injected():
    sql = "SELECT pd_nm FROM domestic_bonds WHERE remaining_days <= 365 ORDER BY applied_yield DESC LIMIT 5"
    fixed, changed = strip_unasked_maturity_cap(sql, "한전 채권 중 수익률 높은 것")
    assert changed and "remaining_days <= 365" not in fixed and "mat_dt >= 20260824" in fixed


def test_between_with_buyable_floor_collapses_to_floor():
    sql = "SELECT pd_nm FROM domestic_bonds WHERE mat_dt BETWEEN 20260824 AND 20291231 ORDER BY mat_dt DESC LIMIT 1"
    fixed, changed = strip_unasked_maturity_cap(sql, "삼성전자 채권 중 만기 제일 긴 것")
    assert changed and "BETWEEN" not in fixed and "mat_dt >= 20260824" in fixed


def test_cap_untouched_when_or_shares_the_where_body():
    sql = "SELECT pd_nm FROM domestic_bonds WHERE (mat_dt <= 20291231 OR mat_dt IS NULL) LIMIT 5"
    assert strip_unasked_maturity_cap(sql, "한전 채권 만기 긴 것") == (sql, False)


def test_cap_guard_ignores_other_tables():
    sql = "SELECT itm_nm FROM public_funds WHERE mat_dt <= 20291231 LIMIT 5"
    assert strip_unasked_maturity_cap(sql, "펀드 만기 긴 것") == (sql, False)


# ── ② 발행사 로마자 약칭 ↔ 한글 음역 접두 확장 ───────────────────────────────────────
def test_latin_acronym_expands_to_both_spellings_as_prefix():
    fixed, fired = expand_issuer_acronym_prefix(SQL2)
    assert fired == ["SK|에스케이"]
    assert "pd_pbcm LIKE '%SK%'" not in fixed
    for br in ("TRIM(pd_pbcm) LIKE 'SK%'", "TRIM(pd_pbcm) LIKE '(주)SK%'",
               "TRIM(pd_pbcm) LIKE '에스케이%'", "TRIM(pd_pbcm) LIKE '(주)에스케이%'"):
        assert br in fixed
    assert "AND bd_tisu_a IS NOT NULL" in fixed                # 괄호 안 나머지 절은 그대로


@pytest.mark.parametrize("lit, latin, ko", [
    ("%에스케이%", "SK", "에스케이"), ("%lg%", "LG", "엘지"), ("%지에스%", "GS", "지에스"),
    ("%CJ%", "CJ", "씨제이"), ("%에이치디%", "HD", "에이치디"), ("KDB%", "KDB", "케이디비"),
])
def test_bidirectional_letter_names(lit, latin, ko):
    fixed, fired = expand_issuer_acronym_prefix(f"SELECT pd_nm FROM domestic_bonds WHERE pd_pbcm LIKE '{lit}' LIMIT 5")
    assert fired == [f"{latin}|{ko}"] and f"LIKE '{latin}%'" in fixed and f"LIKE '(주){ko}%'" in fixed


@pytest.mark.parametrize("lit", ["%한국전력공사%", "%SK이노베이션%", "%삼성%", "%S%", "%ABCDE%", "%S%K%", "%현대%"])
def test_concrete_or_non_acronym_literals_are_left_alone(lit):
    sql = f"SELECT pd_nm FROM domestic_bonds WHERE pd_pbcm LIKE '{lit}' LIMIT 5"
    assert expand_issuer_acronym_prefix(sql) == (sql, [])


def test_trimmed_and_qualified_forms_are_recognised():
    sql = "SELECT pd_nm FROM domestic_bonds WHERE TRIM(domestic_bonds.pd_pbcm) LIKE '%LG%' LIMIT 5"
    fixed, fired = expand_issuer_acronym_prefix(sql)
    assert fired == ["LG|엘지"] and "TRIM(domestic_bonds.pd_pbcm) LIKE" not in fixed


# ── ③ 정렬 축 혼동쌍 표 ─────────────────────────────────────────────────────────────
def test_balance_question_swaps_total_issue_to_balance():
    fixed, changed = ensure_sort_axis(SQL2, Q2)
    assert changed
    assert "ORDER BY MAX(isu_bal_amt) DESC" in fixed
    assert ", isu_bal_amt FROM" in fixed                      # SELECT 병기
    assert "isu_bal_amt > 0" not in fixed                     # DESC 엔 양수 조건을 넣지 않는다


def test_balance_ascending_adds_positive_filter():
    sql = "SELECT pd_nm, bd_tisu_a FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 ORDER BY bd_tisu_a ASC LIMIT 5"
    fixed, changed = ensure_sort_axis(sql, "발행잔액이 가장 적은 채권 5개")
    assert changed and "ORDER BY isu_bal_amt ASC" in fixed and "isu_bal_amt > 0" in fixed


def test_total_issue_question_swaps_balance_to_total_issue():
    sql = "SELECT pd_nm, isu_bal_amt FROM domestic_bonds ORDER BY isu_bal_amt DESC LIMIT 5"
    fixed, changed = ensure_sort_axis(sql, "총발행액이 큰 채권 5개")
    assert changed and "ORDER BY bd_tisu_a DESC" in fixed


def test_coupon_axis_behaviour_unchanged():
    sql = "SELECT pd_nm, applied_yield FROM domestic_bonds ORDER BY MAX(applied_yield) DESC LIMIT 5"
    fixed, changed = ensure_sort_axis(sql, "표면금리 높은 순으로 5개")
    assert changed and "ORDER BY MAX(srfc_irt)" in fixed


@pytest.mark.parametrize("q, sql", [
    ("표면금리 5% 넘는 것 중 만기 짧은 순", "SELECT pd_nm FROM domestic_bonds WHERE srfc_irt > 5 ORDER BY mat_dt ASC LIMIT 5"),
    ("발행잔액이랑 총발행액 둘 다 큰 채권", "SELECT pd_nm FROM domestic_bonds ORDER BY bd_tisu_a DESC LIMIT 5"),
    ("발행잔액 큰 채권 몇 개야", "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds ORDER BY bd_tisu_a DESC LIMIT 1"),
    ("수익률 높은 채권", "SELECT pd_nm FROM domestic_bonds ORDER BY applied_yield DESC LIMIT 5"),
])
def test_sort_axis_does_not_touch_other_axes(q, sql):
    assert ensure_sort_axis(sql, q) == (sql, False)


def test_fmt_won():
    assert _fmt_won("700000000000") == "7,000억원"
    assert _fmt_won("600009437500") == "6,000.1억원"
    assert _fmt_won("0") == "미수록" and _fmt_won("n/a") == "n/a"


# ── DB 실측 — 두 문항의 정답이 실제로 나오는가 ──────────────────────────────────────
pytestmark_db = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytestmark_db
def test_q1_after_guard_returns_true_longest_kepco_bond():
    fixed, _ = strip_unasked_maturity_cap(SQL1, Q1)
    con = sqlite3.connect(db_path())
    try:
        row = con.execute(fixed).fetchone()
    finally:
        con.close()
    assert row[0] == "한국전력공사채권1184" and int(row[3]) == 20520421


@pytestmark_db
def test_q2_after_guards_covers_korean_spelled_affiliates():
    fixed, _ = expand_issuer_acronym_prefix(SQL2)
    fixed, _ = ensure_sort_axis(fixed, Q2)
    con = sqlite3.connect(db_path())
    try:
        rows = con.execute(fixed).fetchall()
        body = fixed[fixed.index("WHERE"):fixed.index("GROUP BY")]
        n = con.execute(f"SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds {body}").fetchone()[0]
    finally:
        con.close()
    assert [r[0] for r in rows] == ["에스케이하이닉스224-2", "SK이노베이션신종자본증권 2(사모/콜/후)", "SK이노베이션 1CB(사모/전환)"]
    assert n == 307
