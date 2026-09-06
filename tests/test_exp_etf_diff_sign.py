# -*- coding: utf-8 -*-
"""괴리율 부호 고지 — 오답 색인 #13 (2026-09-06 재생 E13). 숫자 옆 한 마디는 코드가 적는다."""
from src.runtime import pipeline as P

SQL = "SELECT pd_abrv_nm, du_diff_rt FROM domestic_etfs WHERE pd_grp_no = 'ETF' ORDER BY ABS(du_diff_rt) DESC LIMIT 1"


def test_note_appended_when_sql_uses_diff_rt():
    out, ok = P.ensure_etf_diff_sign_note("괴리율이 가장 큰 ETF는 ACE 미국배당다우존스 (-3.2%) 입니다.", SQL)
    assert ok and "고평가" in out and "저평가" in out and out.startswith("괴리율이 가장 큰")


def test_silent_when_answer_already_explains_or_sql_unrelated():
    a = "괴리율 +3.2% 로 고평가 상태입니다."
    assert P.ensure_etf_diff_sign_note(a, SQL) == (a, False)
    other = "SELECT pd_abrv_nm FROM domestic_etfs ORDER BY du_last_aum DESC LIMIT 5"
    assert P.ensure_etf_diff_sign_note("순자산 1위 KODEX 200", other) == ("순자산 1위 KODEX 200", False)
    bond = "SELECT pd_nm FROM domestic_bonds WHERE du_diff_rt > 0 LIMIT 5"
    assert P.ensure_etf_diff_sign_note("x", bond) == ("x", False)


def test_idempotent():
    once, _ = P.ensure_etf_diff_sign_note("괴리율 1위 A", SQL)
    assert P.ensure_etf_diff_sign_note(once, SQL) == (once, False)
