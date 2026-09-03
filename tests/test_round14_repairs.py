"""14R 수리 회귀 테스트 — `docs/recheck_2026-09-03_round14_plan.md` 의 (b) 열 이름을 그대로 쓴다.

각 테스트는 심사관 §③ 의 **일반 규칙 하나**를 고정한다. 문항별 예외가 아니라 부류를 고정하는 것이 목적이라
실측 SQL 을 재료로 쓰되 검사는 규칙 형태로 한다.
"""

from __future__ import annotations

import re

from src.runtime import pipeline as P


# ── P1-a · gold ③-1 (부류 Z″) — 사용자 브랜드 조건은 상품명 축에서 사라질 수 없다 ──────────────
def test_etf_brand_token_postcondition():
    q = "KODEX AI 로봇 ETF 알려줘"
    sql = ("SELECT pd_nm, pd_abrv_nm, du_last_aum FROM domestic_etfs "
           "WHERE pd_nm LIKE '%AI%' AND pd_nm LIKE '%로봇%' LIMIT 30")
    out, fixed = P.ensure_etf_brand_token(sql, q)
    assert fixed and "KODEX" in out
    # 멱등 — 브랜드가 이미 있으면 불개입
    assert P.ensure_etf_brand_token(out, q)[1] is False


def test_etf_brand_token_skips_when_brand_present_or_absent():
    # ⓐ 브랜드가 이미 술어에 있으면 불개입
    sql = "SELECT pd_abrv_nm FROM domestic_etfs WHERE TRIM(pd_abrv_nm) = 'KODEX 200' LIMIT 1"
    assert P.ensure_etf_brand_token(sql, "KODEX 200 알려줘")[1] is False
    # ⓑ 질문에 브랜드가 없으면 불개입 (OFFICIAL-004 형 — 테마 조건검색)
    sql2 = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_nm LIKE '%우주항공%' LIMIT 30"
    assert P.ensure_etf_brand_token(sql2, "우주항공 테마 ETF 정리해줘")[1] is False
    # ⓒ 브랜드가 둘이면 비교 질의라 불개입 (AND 로 이으면 모수가 0이 된다)
    assert P.ensure_etf_brand_token(sql2, "KODEX 와 TIGER ETF 비교해줘")[1] is False
    # ⓓ 이름 축 필터가 없으면 이름 질의가 아니다 — 불개입
    sql3 = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_sale_yn = 1 ORDER BY du_last_aum DESC LIMIT 5"
    assert P.ensure_etf_brand_token(sql3, "KODEX 순자산 큰 ETF")[1] is False


def test_etf_brand_tokens_come_from_db():
    brands = P._etf_brand_tokens()
    assert "KODEX" in brands and "TIGER" in brands
    assert all(len(b) >= 2 for b in brands)


# ── P1-b · gold ③-2 — 정확일치·유사 판정은 공백 정규화 후에 한다 ──────────────────────────────
def test_suggest_similar_reads_spaceless_like():
    """LIKE 로 쪼개진 이름 술어도 되묻기 재료다 — 띄어쓰기 하나로 안전망이 꺼지면 안 된다."""
    sql = ("SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_nm LIKE '%AI%' AND pd_nm LIKE '%로봇%' "
           "AND REPLACE(pd_nm,' ','') LIKE '%KODEX%' LIMIT 30")
    cand = P._suggest_similar_products(sql)
    assert cand and all("KODEX" in c for c in cand)
    # 등호 경로(형제 OFFICIAL-NA-003)는 종전 동작 그대로
    eq = "SELECT pd_abrv_nm FROM domestic_etfs WHERE TRIM(pd_abrv_nm) = 'KODEX AI로봇' LIMIT 1"
    assert P._suggest_similar_products(eq)
