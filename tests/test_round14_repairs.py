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


# ── P2-e · 재검 ③-3 (부류 AD) — 억원은 SQL 이 구운 열을 조립기가 그대로 쓴다 ─────────────────
_LK_SQL = ("SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS \"클래스수\", "
           "SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS \"판매중클래스수\", "
           "CAST(SUM(fd_nast_suma) AS INTEGER) AS fd_nast_suma, "
           "CAST(ROUND(SUM(fd_nast_suma)/100000000.0) AS INTEGER) || '억원' AS \"순자산_억원\", "
           "MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds WHERE prvo_pbff_desc = '공모' "
           "AND (TRIM(or_co_xtn_itt_cd) = '00040067' AND REPLACE(itm_nm,' ','') LIKE '%테스트%' "
           "AND (REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2호*' OR REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2[([]*')) "
           "GROUP BY 1 LIMIT 30")
_LK_HEAD = "대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | fd_nast_suma | 순자산_억원 | 대표번호"


def test_lookup_answer_uses_baked_eok():
    """절사로 남아 있던 조립기가 SQL 이 구운 ROUND 열을 그대로 옮긴다 (254,000,000원 → 2억 아니라 3억)."""
    rows = _LK_HEAD + "\nKR1 | 테스트펀드 | 1 | 1 | 254000000 | 3억원 | R1"
    out = P._lookup_answer(_LK_SQL, rows, 1, "테스트", [])
    assert out and "순자산 3억원" in out and "2억원" not in out


def test_lookup_answer_rounds_when_no_baked_column():
    """구운 열이 없을 때만 조립기가 굽고, 그때도 ROUND 다."""
    head = "대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | fd_nast_suma | 대표번호"
    rows = head + "\nKR1 | 테스트펀드 | 1 | 1 | 254000000 | R1"
    out = P._lookup_answer(_LK_SQL, rows, 1, "테스트", [])
    assert out and "순자산 3억원" in out


# ── P4-g · 재검 ③-4 (Y14) — 중첩 OR 때문에 개별 조회 조립기가 꺼지지 않는다 ───────────────────
def test_lookup_answer_fires_with_nested_or():
    """호수 경계 가드가 심은 **중첩** OR 이 이름 조회 판정을 꺼뜨리면 안 된다 — 가드가 늘 때마다 재발할 구조였다."""
    assert P._has_name_filter(_LK_SQL) is True
    rows = _LK_HEAD + "\nKR5117450025 | 신한중국의꿈증권자투자신탁제2호(H)[주식]종류A | 4 | 4 | 106915036337 | 1,069억원 | 030480108616"
    out = P._lookup_answer(_LK_SQL, rows, 1, "신한중국의꿈증권자투자신탁제2호", [])
    assert out and "1,069억원" in out and "클래스 4개" in out and P.gate.DATA_CUTOFF in out


def test_has_name_filter_still_rejects_top_level_or():
    """태그 ∪ 이름 목록(KG-021)은 여전히 이름 조회가 아니다 — 최상위 OR 는 종전대로 걸린다."""
    from src.runtime import loader
    loader.load_context()
    sql = ("SELECT itm_nm FROM public_funds WHERE (',' || prfd_attr_cds || ',' LIKE '%,TWN,%' "
           "OR REPLACE(itm_nm,' ','') LIKE '%대만%') AND sale_yn = '판매중' LIMIT 30")
    assert P._has_name_filter(sql) is False


# ── P3-a · KG ③-5 (AA16 · 보류 해제) — 모수를 흉내 낸 SELECT CASE 는 모수 절로 승격한다 ────────
def test_base_population_promotes_full_case():
    import sqlite3
    sql = ("SELECT trusc_xtn_itt_cd, SUM(CASE WHEN sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
           "THEN 1 ELSE 0 END) AS cnt, COUNT(DISTINCT " + P._FUND_KEY_EXPR + ") AS \"펀드수\", "
           "COUNT(*) AS \"클래스수\" FROM public_funds GROUP BY trusc_xtn_itt_cd ORDER BY \"펀드수\" DESC LIMIT 5")
    out, ok = P.ensure_fund_base_population(
        sql, "공모펀드를 가장 많이 수탁하는 수탁사 상위 5개를 펀드 수 기준으로 알려줘", post=True)
    assert ok and "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모'" in out
    con = sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)
    try:
        got = [(r[0], r[2]) for r in con.execute(out)]
    finally:
        con.close()
    assert got == [("00020054", 714), ("00020004", 516), ("00020027", 465),
                   ("00020081", 399), ("00020088", 307)]        # 심사관 실측 gold · 순위도 바로잡힌다


def test_base_population_leaves_lookup_case_alone():
    """개별 조회 묶기가 심는 `판매중클래스수` CASE 는 sale_yn 하나뿐이라 승격 대상이 아니다 —
    동결선 S5·W5·X18 의 where 가 바뀌면 안 된다."""
    sql = ("SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS \"클래스수\", "
           "SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS \"판매중클래스수\" FROM public_funds "
           "WHERE prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' GROUP BY 1 LIMIT 30")
    assert P.ensure_fund_base_population(sql, "코어테크 펀드 클래스수 알려줘", post=True) == (sql, False)


# ── P4-a · KG ③-1 — 가드 체인을 UNION 가지 단위로 ─────────────────────────────────────────
def test_union_branch_guards():
    import sqlite3
    from src.runtime import loader
    loader.load_context()
    con = sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)
    try:
        # X8 — 펀드 절은 공백 무시 벤치마크, ETF 절은 지수 정본 축 + 기본모수
        x8 = ("SELECT 'A' AS 구분, COUNT(*) FROM public_funds WHERE prvo_pbff_desc = '공모' "
              "AND bmrk_nm LIKE '%S&P500%' AND sale_yn = '판매중' "
              "UNION ALL SELECT 'B' AS 구분, COUNT(*) FROM domestic_etfs "
              "WHERE ref_base_index LIKE '%S&P500%' AND pd_sale_yn = 1 LIMIT 30")
        s, _ = P.ensure_spaceless_name_match(x8)
        s, notes = P.apply_union_branch_guards(s, "S&P500을 벤치마크로 쓰는 공모펀드와 S&P500 추종 국내 ETF는 각각 몇 개야?")
        # 16R KG ③-1 — 펀드 가지도 펀드단위 집계로 교체된다: 펀드 57 / 클래스 188 · ETF 24
        assert notes and [tuple(r)[1:] for r in con.execute(s)] == [(57, 188), (24, None)]

        # KG-026 — 오염 컬럼 cu_base_index 가 정본 축으로 교체돼 거짓 부재(0)가 사라진다
        kg26 = ("SELECT 'A' AS 분류, COUNT(*) FROM public_funds WHERE bmrk_nm IN ('KOSPI200') "
                "AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' "
                "UNION ALL SELECT 'B', COUNT(*) FROM domestic_etfs WHERE cu_base_index = 'KOSPI200' "
                "AND pd_sale_yn = 1 AND pd_tr_yn = 0 LIMIT 30")
        out, notes26 = P.apply_union_branch_guards(kg26, "KOSPI200을 추종하는 국내 ETF는 몇 개야?")
        assert notes26 and [r[1] for r in con.execute(out)][1] == 34      # gold ETF 34 (펀드 가지는 질문 문언상 불개입)

        # X9 — 펀드 가지에 기본모수가 붙는다(3,296 → 2,066 = gold 클래스)
        x9 = ("SELECT 'A' AS 구분, COUNT(*) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' "
              "AND prvo_pbff_desc = '공모' UNION ALL SELECT 'B', COUNT(*) FROM domestic_etfs "
              "WHERE ref_fund_mgmt_co = 'Mirae Asset Global Investments Co Ltd' LIMIT 30")
        out9, _ = P.apply_union_branch_guards(x9, "미래에셋자산운용이 운용하는 공모펀드와 국내 ETF는 각각 몇 개야?")
        # 16R: 펀드 823 / 클래스 2,066 · ETF 230
        assert [tuple(r)[1:] for r in con.execute(out9)] == [(823, 2066), (230, None)]
    finally:
        con.close()
    # 단일 SELECT 는 분해 대상이 아니다
    single = "SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' LIMIT 1"
    assert P.apply_union_branch_guards(single, "몇 개야") == (single, [])


def test_spaceless_bmrk_nm():
    """X8 — 벤치마크 이름도 표기 공백이 제각각이다('S&P500' vs 'S&P 500'). 등호는 확장하지 않는다."""
    out, ok = P.ensure_spaceless_name_match("SELECT 1 FROM public_funds WHERE bmrk_nm LIKE '%S&P500%'")
    assert ok and "REPLACE(bmrk_nm,' ','')" in out
    eq = "SELECT 1 FROM public_funds WHERE bmrk_nm = 'KOSPI200'"
    assert P.ensure_spaceless_name_match(eq) == (eq, False)


# ── P4-a 짝 · KG ③-11 — 컬럼 존재 검사도 가지별 FROM 기준 ────────────────────────────────
def test_unknown_columns_per_scope():
    from src.runtime import guard, loader
    ctx = loader.load_context()
    x15 = ("SELECT 'A' AS 분류, COUNT(*) FROM public_funds WHERE prvo_pbff_desc = '공모' "
           "AND wu_inv_rgn = '중국' GROUP BY 1 "
           "UNION ALL SELECT 'B', COUNT(*) FROM domestic_etfs WHERE wu_inv_rgn = '국내' GROUP BY 1 LIMIT 30")
    assert "wu_inv_rgn" in guard.unknown_columns(x15, ctx)     # 펀드 가지엔 없는 컬럼이다(X15 실행 오류)
    ok = "SELECT itm_nm, fd_nast_suma FROM public_funds WHERE sale_yn = '판매중' LIMIT 5"
    assert guard.unknown_columns(ok, ctx) == []


# ── P4-h · KG ③-8 (Z16) / P3-b · KG ③-7 (X12) — 운용사 코드 집합 ────────────────────────────
def _count_sql(code: str) -> str:
    return ("SELECT COUNT(DISTINCT " + P._FUND_KEY_EXPR + ") AS \"펀드수\", COUNT(*) AS \"클래스수\" "
            "FROM public_funds WHERE sale_yn = '판매중' AND (TRIM(or_co_xtn_itt_cd) = '" + code + "' "
            "AND prvo_pbff_desc = '공모') LIMIT 30")


def test_label_official_duplicate_codes():
    """Z16 — 같은 정본 이름의 or_co 코드는 전부 IN (실측 4쌍: 키움투자자산운용 00080052·00040013 등)."""
    import sqlite3
    from src.runtime import loader
    loader.load_context()
    sql = _count_sql("00080052")
    con = sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)
    try:
        assert con.execute(sql).fetchone() == (97, 308)           # 부족값
        # 16R KG ③-5 — 확장은 질문이 그 그룹의 **정본 이름**을 부를 때만 (2인자가 mgmt 튜플 → 질문 문자열로 바뀌었다)
        out, ok = P.ensure_org_label_codes(sql, "키움투자자산운용이 운용하는 공모펀드는 몇 개야?")
        assert ok and con.execute(out).fetchone() == (112, 354)   # gold 112펀드/354클래스
    finally:
        con.close()
    # 브랜드 어간 질의에는 개입하지 않는다 — 정본 이름이 브랜드와 다를 수 있다(구상호 '슈로더' → 키움투자자산운용)
    assert P.ensure_org_label_codes(sql, "슈로더가 운용하는 공모펀드는 몇 개야?")[1] is False


def test_offshore_included_when_asked():
    """X12 — '역외펀드까지 포함하면' 이면 역외 법인 코드를 합산한다. 문형이 없으면 종전대로 분리(S9·T11·KG-031)."""
    import sqlite3
    sql = _count_sql("00040013")
    mgmt = ("슈로더", "00040013", "슈로더자산운용")
    con = sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)
    try:
        assert con.execute(sql).fetchone() == (15, 46)
        out, note = P.ensure_mgmt_code_predicate(sql, "슈로더가 운용하는 공모펀드는 역외펀드까지 포함하면 몇 개야?", mgmt)
        assert note and con.execute(out).fetchone() == (28, 59)   # gold
        same, note2 = P.ensure_mgmt_code_predicate(sql, "슈로더가 운용하는 공모펀드는 몇 개야?", mgmt)
        assert note2 is None and con.execute(same).fetchone() == (15, 46)
    finally:
        con.close()


# ── P4-f · 재검 ③-2 (부류 E) — 개별 조회의 클래스수 모수는 값 술어와 무관하다 ─────────────────
def test_lookup_grouping_class_count_off_value():
    """S12 교과서 사례: `fd_yr1_ern_r IS NOT NULL AND > -100` 이 클래스수를 NULL 수만큼 깎았다(10→9·5→3·13→12).
    값 술어를 집계 안쪽으로 옮기면 COUNT 는 기본모수 전체를 세고 표시 범위는 그대로다."""
    import sqlite3
    from src.runtime import loader
    loader.load_context()
    sql = ("SELECT itm_nm, fd_yr1_ern_r FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%코어테크%' "
           "AND sale_yn='판매중' AND prvo_pbff_desc='공모' AND fd_yr1_ern_r IS NOT NULL "
           "AND fd_yr1_ern_r > -100 LIMIT 30")
    out, ok = P.ensure_fund_lookup_grouping(sql, "코어테크 펀드 1년 수익률 알려줘")
    assert ok and "MAX(CASE WHEN fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r > -100 THEN fd_yr1_ern_r END)" in out
    con = sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)
    try:
        rows = con.execute(out).fetchall()
    finally:
        con.close()
    assert [r[2] for r in rows] == [10, 4, 5, 5, 13, 4]              # 심사관 S12 gold 클래스수
    assert (rows[0][4], rows[0][5]) == (189.77, 187.09)              # 표시 범위는 불변
    assert (rows[4][4], rows[4][5]) == (17.73, -41.31)


def test_lookup_grouping_untouched_without_value_predicate():
    """값 술어가 없는 개별 조회(U10 등급 질의 — 부류 E 대조군)는 SQL 모양이 종전과 같아야 한다."""
    sql = ("SELECT itm_nm, zrin_fd_ivst_risk_gcd FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋베트남%' "
           "AND sale_yn='판매중' AND prvo_pbff_desc='공모' LIMIT 30")
    out, ok = P.ensure_fund_lookup_grouping(sql, "미래에셋베트남 펀드 위험등급 알려줘")
    assert ok and "CASE WHEN zrin_fd_ivst_risk_gcd" not in out


# ── P4-c · KG ③-3·④ (KG-008) — 가드 별칭 유일화 + 랭킹은 기계 조립 ────────────────────────
def _run(sql):
    import sqlite3
    con = sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        con.close()
    return " | ".join(cols) + "\n" + "\n".join(" | ".join(str(v) for v in r) for r in rows), len(rows)


def test_entity_count_alias_unique_and_assembled():
    from src.runtime import loader
    loader.load_context()
    base = ("SELECT trim(trusc_xtn_itt_cd) as 수탁회사명, SUM(fd_nast_suma) as 수탁금액, COUNT(*) as 펀드수 "
            "FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY 1 "
            "ORDER BY 2 DESC LIMIT 3")
    sql, ok = P.ensure_fund_entity_count_ranking(base, "공모펀드를 가장 많이 수탁하는 수탁사 상위 3개 알려줘")
    # 16R KG ③-3 — 접미로 피하지 않고 충돌한 HCX 항목을 지운다(결과 열에 동명이 남으면 답변기가 그쪽을 읽는다)
    assert ok and '"펀드수__g"' not in sql and 'ORDER BY "펀드수" DESC' in sql and sql.count('AS "펀드수"') == 1
    assert P.ensure_fund_entity_count_ranking(sql, "공모펀드를 가장 많이 수탁하는 수탁사 상위 3개 알려줘")[1] is False
    rows, n = _run(sql)
    out = P._entity_count_rank_answer(sql, rows, n)
    assert out and out.splitlines()[2].startswith("1. 홍콩상하이은행(00020054): 펀드 714개") or "714" in out
    assert "714" in out and "516" in out and "465" in out               # gold · SQL 행 순서 그대로
    assert out.index("714") < out.index("516") < out.index("465")


def test_label_code_columns_skips_aggregate_items():
    """가드가 심은 펀드키 식(COUNT(DISTINCT printf(... or_co_xtn_itt_cd ...)))은 코드 열이 아니다."""
    from src.runtime import loader
    loader.load_context()
    sql = ('SELECT trim(trusc_xtn_itt_cd) AS 수탁회사명, COUNT(DISTINCT ' + P._FUND_KEY_EXPR + ') AS "펀드수" '
           "FROM public_funds WHERE sale_yn = '판매중' GROUP BY 1 LIMIT 1")
    rows = "수탁회사명 | 펀드수\n00020054 | 714"
    out, touched = P.label_code_columns(rows, sql)
    assert touched == ["수탁회사명"] and "| 714" in out and "코드 714" not in out


# ── P4-e · KG ③-9 (X22) — 집계 1행의 0 은 '없음' 이다 ────────────────────────────────────────
def test_zero_count_with_extra_columns():
    """X22: `COUNT(*) as cnt, COALESCE(trusc_xtn_itt_cd,'정보 없음')` 1행이 표시 열 때문에 HCX 로 넘어가
    리터럴 '정보 없음' 을 값으로 되읽고 오거절이 됐다. 첫 항목이 집계면 0 은 '없음' 이다."""
    sql = ("SELECT COUNT(*) as cnt, COALESCE(public_funds.trusc_xtn_itt_cd, '정보 없음') as actual "
           "FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040035' "
           "AND TRIM(trusc_xtn_itt_cd) = '00020004' AND sale_yn = '판매중' LIMIT 1")
    out = P._zero_count_answer(sql, "cnt | actual\n0 | 정보 없음", 1)
    assert out and "확인되지 않습니다" in out and "정보 없음" not in out
    assert P._zero_count_answer(sql, "cnt | actual\n5 | 00020004", 1) is None      # 양수는 불개입


# ── KG ③-10 (Z18) — 전사 강제는 원시 행이 아니라 답변 스키마로 ───────────────────────────────
def test_rows_answered_no_raw_dump():
    from src.runtime import loader
    loader.load_context()
    # 읽을 수 있는 표시 축이 하나도 없으면 전사하지 않는다(원시 덤프보다 거절문이 낫다)
    rows = "or_co_xtn_itt_cd | itm_no\n00040010 | KR5100000001"
    a = "요청하신 정보를 확인할 수 없습니다."
    assert P.ensure_rows_answered(a, rows, 1) == (a, False)
    # 센티널 값(KR0000000000)은 옮기지 않는다
    rows2 = "itm_nm | 대표번호\n테스트펀드 | KR0000000000"
    out, ok = P.ensure_rows_answered(a, rows2, 1)
    assert ok and "테스트펀드" in out and "KR0000000000" not in out


# ── gold ③-11 · ③-23 — 머리줄 라벨은 코드가 아니라 이름 · 이름 자르기는 괄호를 열어 두지 않는다 ──
def test_rank_filter_label_uses_name_column():
    from src.runtime import loader
    loader.load_context()
    sql = ("SELECT itm_no FROM public_funds WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
           "AND zrin_fd_ivst_risk_gcd = 1.0 GROUP BY 1 ORDER BY 2 DESC LIMIT 5")
    assert P._rank_filter_labels(sql) == ["매우 높은 위험"]      # FND-002 must_include


def test_fund_stem_keeps_balanced_name():
    assert P._fund_stem("신한BEST신종법인용MMFGS-2호(운용) 종류C") == "신한BEST신종법인용MMFGS-2호(운용)"
    assert P._fund_stem("미래에셋코어테크증권자투자신탁(주식) 종류A") == "미래에셋코어테크증권자투자신탁(주식)"
    # 2자 이하로 줄면 원문을 쓴다
    assert len(P._fund_stem("하나 종류C")) > 2


# ── 재검 ③-7 — 목록 답변은 같은 대표번호 행을 한 줄로 접는다 (8문항) ──────────────────────────
def test_list_answer_folds_by_rptt():
    from src.runtime.pipeline import answer_question
    from src.runtime import loader
    ctx = loader.load_context()
    sql = ("SELECT DISTINCT itm_no, itm_nm, prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' "
           "AND ',' || prfd_attr_cds || ',' LIKE '%,CHN,%' AND sale_yn = '판매중' LIMIT 30")

    class Pl:
        calls = 0

        def plan_sql(self, q, g):
            return sql

        def compose_answer(self, q, rows, answer_rules=""):
            Pl.calls += 1
            return "x"

    r = answer_question("T14-LIST", "중국에 투자하는 공모펀드 알려줘", planner=Pl(), ctx=ctx)
    assert Pl.calls == 0                                   # 기계 조립 — HCX 0회
    # 🔴 16R 재검 ③-1 이 접기를 SQL 층(GROUP BY rptt)으로 옮겼다 — 머리줄의 「대표번호 기준」은 전체값(106)이다
    assert "대표번호 기준 106건" in r.answer
    assert "전체 248개(클래스 560개)" in r.answer            # 펀드키 축 「전체 N개」는 그대로(리드 판단 대기)
    body = [ln for ln in r.answer.splitlines() if re.match(r"\d+\. ", ln)]
    assert len(body) == 30 and len({ln.split(":")[0] for ln in body}) == 30   # 중복 줄 0


# ── gold ③-12 (FND-R02) — 축을 바꿔 답했으면 반드시 밝힌다 ────────────────────────────────
def test_missing_axis_note():
    note = P.missing_axis_note("SELECT fd_wk1_ern_r FROM public_funds LIMIT 5")
    assert note and "1주" in note and "없" in note                 # must_include 두 낱말
    assert P.missing_axis_note("SELECT fd_mm1_ern_r FROM public_funds LIMIT 5") is None
