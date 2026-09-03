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


# ── P1-c · gold ③-18·③-17 — 금지 문형(권유·전망·외부 출처 안내) 은 경로와 무관하게 걷는다 ──────
def test_strip_disclaimer_advice_forms():
    tails = {
        # UNANS-001 꼬리
        "투자 전 각 상품의 특성과 위험 요소를 충분히 이해하고 확인하는 것이 중요합니다.": True,
        "시장 상황에 따라 성과가 달라질 수 있으므로 신중하게 고려하여 투자 결정을 내리시기 바랍니다.": True,
        # OFFICIAL-004 꼬리
        "ETF 투자는 시장 변동성에 따라 손실이 발생할 수 있으므로 신중하게 결정해야 합니다.": True,
        "각 ETF는 해당 테마를 대표하는 주식이나 지수에 투자하여 수익을 추구합니다.": True,
        # OFFICIAL-002 Refuse 꼬리
        "해당 정보는 금융기관의 공식 웹사이트나 관련 보고서를 통해 확인하실 수 있습니다.": True,
        # X2·X14 내용 없는 마무리문
        "위의 정보를 통해 각 펀드의 특성을 확인할 수 있습니다.": True,
    }
    for tail, expected in tails.items():
        body = "1. 삼성MMF법인제1호: 순자산 124,295억원 · 클래스 4개\n" + tail
        out, changed = P.strip_disclaimer(body)
        assert changed is expected, tail
        assert "124,295억원" in out          # 값·목록은 건드리지 않는다


def test_strip_disclaimer_keeps_machine_assembly():
    body = ("순자산 상위 3개 공모펀드입니다 (판매중·공모 기준, 펀드 = 대표예탁원번호 기준, 기준일 2026-08-24).\n"
            "1. 삼성MMF법인제1호: 순자산 124,295억원 · 클래스 4개")
    assert P.strip_disclaimer(body) == (body, False)


# ── P1-d · gold ③-20 — 폐기 컬럼은 SELECT 목록에서도 폐기한다 ────────────────────────────────
def test_etf_mgmt_canon_select_list():
    sql = ("SELECT pd_nm, pd_abrv_nm, cu_fund_mgmt_co, du_last_aum FROM domestic_etfs "
           "WHERE pd_nm LIKE '%로봇%' LIMIT 30")
    out, fixed = P.ensure_etf_mgmt_canon(sql)
    assert fixed and "cu_fund_mgmt_co" not in out and "ref_fund_mgmt_co" in out
    # 항목 수 불변 — 위치 ORDER BY 가 깨지지 않는다
    assert len(P._split_select_items(out[out.upper().find("SELECT") + 6:out.upper().find(" FROM")])) == 4
    assert P.ensure_etf_mgmt_canon(out)[1] is False
