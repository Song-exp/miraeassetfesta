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


# ── P2-a · gold ③-3 (부류 AC) — 정렬축 감싸기는 SELECT 항목 단위로 ──────────────────────────
def test_wrap_sort_col_expression_item():
    """FND-005: 산술식 항목은 **항목 전체**를 감싼다 — 첫 토큰만 감싸면 문법이 깨진다."""
    head = ("SELECT itm_no, TRIM(itm_nm), or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r "
            "+ ofwk_trus_rwrd_r AS tot_commission_rate ")
    out, wrapped, in_func = P._wrap_sort_col(head, "or_co_rwrd_r", "MIN")
    assert wrapped
    assert "MIN(or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r) AS tot_commission_rate" in out
    assert "AS or_co_rwrd_r +" not in out          # 13R 파손 형태가 아니다
    assert in_func is True                          # 별칭이 컬럼명과 달라 ORDER BY 이름도 감싸야 한다


def test_wrap_sort_col_table_alias():
    """FND-010: `p.fd_nast_suma` 를 `p.MAX(...)` 로 부수지 않는다."""
    head = "SELECT DISTINCT p.itm_no, p.itm_nm, p.fd_nast_suma, p.fd_last_dstb_r "
    out, wrapped, _ = P._wrap_sort_col(head, "fd_nast_suma", "MAX")
    assert wrapped and "MAX(p.fd_nast_suma) AS fd_nast_suma" in out and "p.MAX(" not in out


def test_wrap_sort_col_gives_up_on_unwrappable():
    # 선두 괄호(UNION 가지) — 분해가 성립하지 않으면 원 head 그대로
    head = "(SELECT '국내 ETF' AS 구분, pd_abrv_nm, du_last_aum "
    assert P._wrap_sort_col(head, "du_last_aum", "MAX") == (head, False, False)
    # 서브쿼리 항목은 손대지 않는다
    head2 = "SELECT itm_no, (SELECT MAX(fd_nast_suma) FROM public_funds) AS fd_nast_suma "
    assert P._wrap_sort_col(head2, "fd_nast_suma", "MAX")[1] is False


def test_fund_rank_representative_produces_valid_sql():
    """13R 무응답 2건의 SQL 이 이제 파싱된다 — 가드가 만든 문법 오류는 우리 잘못이다."""
    import sqlite3
    for sql in (
        "SELECT itm_no, TRIM(itm_nm), or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r "
        "AS tot_commission_rate FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
        "GROUP BY or_co_xtn_itt_cd ORDER BY 3 ASC LIMIT 5",
        "SELECT DISTINCT p.itm_no, p.itm_nm, p.fd_nast_suma, p.fd_last_dstb_r FROM public_funds p "
        "WHERE p.sale_yn = '판매중' GROUP BY or_co_xtn_itt_cd ORDER BY 3 DESC LIMIT 5",
    ):
        out, _ = P.ensure_fund_rank_representative(sql, "총보수가 가장 낮은 공모펀드 5개")
        con = sqlite3.connect(str(P.db_path()) if hasattr(P, "db_path") else "data/financial_products.db")
        try:
            con.execute("EXPLAIN " + out)       # 문법 오류면 여기서 터진다
        finally:
            con.close()


# ── P2-b · gold ③-4 — SELECT 편집 가드는 단일 SELECT 에서만 ────────────────────────────────
def test_single_select_helper():
    assert P._single_select("SELECT a FROM t LIMIT 1")
    assert not P._single_select("(SELECT a FROM t) UNION ALL (SELECT b FROM u)")
    assert not P._single_select("SELECT a FROM t UNION SELECT b FROM u")


def test_amount_eok_skips_union():
    """CROSS-003: 억원 병기 가드가 UNION 문장을 부수지 않는다."""
    sql = ("(SELECT '국내 ETF' AS 구분, pd_abrv_nm, du_last_aum FROM domestic_etfs "
           "WHERE pd_sale_yn = 1 ORDER BY 3 DESC LIMIT 5) UNION ALL "
           "(SELECT '공모펀드', itm_nm, fd_nast_suma FROM public_funds WHERE sale_yn = '판매중' "
           "ORDER BY 3 DESC LIMIT 5)")
    assert P.ensure_amount_eok_columns(sql) == (sql, False)


# ── P2-c · gold ③-5 — 위치 ORDER BY 는 SELECT 열 수와 대조한다 ──────────────────────────────
def test_order_by_position_out_of_range():
    bad = ("SELECT pd_abrv_nm, cu_lev_fector, pd_risk_nm, wu_inv_ast_type, pd_nm FROM domestic_etfs "
           "WHERE pd_sale_yn = 1 ORDER BY 6 DESC LIMIT 1")
    why = P.validate_sql(bad)
    assert why and "위치 ORDER BY" in why
    ok = bad.replace("ORDER BY 6", "ORDER BY 5")
    assert P.validate_sql(ok) is None
    # UNION 은 첫 가지로 판정하면 오탐이라 불개입
    assert P._order_by_position_overflow("(SELECT a, b FROM t) UNION ALL (SELECT c, d FROM u) ORDER BY 2") is None


# ── P2-d · 재검 ③-1 — 역조회 운용사 코드는 등호로 쓰지 않는다 ──────────────────────────────
_MGMT = ("삼성", "00040010", "삼성자산운용")


def test_mgmt_code_predicate_dropped_when_name_has_brand():
    """S3: 이름 리터럴이 브랜드를 이미 품으면 코드 등호는 정보가 0이고 정답 행을 자른다."""
    import sqlite3
    sql = ("SELECT MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS c FROM public_funds "
           "WHERE TRIM(or_co_xtn_itt_cd) = '00040010' AND REPLACE(itm_nm,' ','') LIKE '%삼성코리아대표%' "
           "AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' "
           "GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), itm_no) LIMIT 30")
    out, note = P.ensure_mgmt_code_predicate(sql, "삼성코리아대표 펀드 1년 수익률 알려줘", _MGMT)
    assert note and "or_co_xtn_itt_cd" not in out and "1=1" not in out
    con = sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute(out)]
    finally:
        con.close()
    assert len(names) == 2                      # gold: 분할매수 1클래스 + 제1호 9클래스
    assert any("제1호" in n for n in names)


def test_mgmt_code_predicate_in_list():
    """W1 형(이름에 브랜드가 없다): 등호가 아니라 브랜드 어간 역조회 코드 전부의 IN."""
    sql = ("SELECT itm_nm FROM public_funds WHERE prvo_pbff_desc = '공모' "
           "AND (TRIM(or_co_xtn_itt_cd) = '00040010' AND REPLACE(itm_nm,' ','') LIKE '%차이나본토%') LIMIT 30")
    out, note = P.ensure_mgmt_code_predicate(sql, "삼성차이나본토 펀드 위험등급 알려줘", _MGMT)
    assert note and "IN (" in out and "'00080135'" in out          # 삼성액티브가 들어온다


def test_mgmt_code_predicate_skips_kg_mapped():
    """KG 가 Organization 으로 확정한 코드(U11·S9)에는 개입하지 않는다 — 우리가 지어낸 코드가 아니다."""
    sql = ("SELECT itm_nm FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080029' "
           "AND REPLACE(itm_nm,' ','') LIKE '%피델리티차이나%' LIMIT 30")
    assert P.ensure_mgmt_code_predicate(sql, "피델리티차이나 펀드 순자산 알려줘", None) == (sql, None)


def test_brand_or_co_codes_offshore_split():
    """역외 종별(0013)은 질문이 역외를 요구할 때만 — S9·T11 은 분리 고지가 gold."""
    assert "00130003" not in P._brand_or_co_codes("슈로더", False)
    assert "00130003" in P._brand_or_co_codes("슈로더", True)


# ── P4-d · KG ③-2 — 확정식은 *같은 컬럼* 잔여 술어도 걷는다 (KG-017) ─────────────────────────
def test_attr_tag_same_column_residual():
    import sqlite3
    from src.runtime import loader
    loader.load_context()
    sql = ("SELECT COUNT(*) AS c FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
           "AND ',' || prfd_attr_cds || ',' LIKE '%,폐쇄,%' LIMIT 30")
    out, ok = P.ensure_fund_attr_tag(sql, "폐쇄형 공모펀드는 몇 개야?")
    assert ok and "'%,폐쇄,%'" not in out and "C104" in out
    con = sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)
    try:
        assert con.execute(out).fetchone()[0] == 6      # gold 3펀드 / 6클래스
    finally:
        con.close()
