# -*- coding: utf-8 -*-
"""8R 수리 회귀 — docs/recheck_2026-09-03_round8_plan.md 항목별.

각 테스트 = 계획표의 (b) 열에 적은 이름. 실패하면 그 항목의 일반 규칙이 깨진 것이다.
"""
import pytest

from src.runtime import pipeline as P
from src.runtime.loader import db_path

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


# ── 항목 1 · KG 부류 D — Answer 가드 상호 무력화 ────────────────────────────────
KG8_SQL = ("SELECT trim(trusc_xtn_itt_cd) as 수탁회사명, SUM(fd_nast_suma) as 수탁금액, COUNT(*) as 펀드수, "
           "CAST(ROUND((SUM(fd_nast_suma))/100000000.0) AS INTEGER) || '억원' AS \"수탁금액_억원\" "
           "FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY 1 ORDER BY 2 DESC LIMIT 3")
KG8_ROWS = ("수탁회사명 | 수탁금액 | 펀드수 | 수탁금액_억원\n"
            "00020054 | 100 | 714 | 1억원\n00020004 | 90 | 516 | 1억원\n00020027 | 80 | 465 | 1억원")


def test_answer_guards_independent():
    """표기 → 숨김 순서라면 두 가드가 모두 걸린다 (7R 은 숨김이 표기를 무음 종료시켰다)."""
    labeled_rows, labeled = P.label_code_columns(KG8_ROWS, KG8_SQL)
    assert labeled == ["수탁회사명"], labeled
    assert "홍콩상하이" in labeled_rows.splitlines()[1], labeled_rows
    kept, hidden = P._hide_answer_columns(labeled_rows, KG8_SQL)
    assert hidden == ["수탁금액"], hidden
    assert "홍콩상하이" in kept.splitlines()[1], kept          # 표기가 숨김 뒤에도 살아 있다

    # 반대 순서(7R 동작)는 여전히 무음 종료 — 그래서 순서를 뒤집은 것이고, 이제 사유가 남는다
    hidden_first, _ = P._hide_answer_columns(KG8_ROWS, KG8_SQL)
    skip: list = []
    _, none = P.label_code_columns(hidden_first, KG8_SQL, skip)
    assert none == [] and skip, (none, skip)


def test_label_skip_silent_only_when_no_code_column():
    """코드 컬럼이 없으면 스킵 사유를 남기지 않는다 (트레이스 잡음 금지)."""
    skip: list = []
    P.label_code_columns("itm_nm\n미래에셋코어테크", "SELECT itm_nm, COUNT(*) FROM public_funds GROUP BY 1", skip)
    assert skip == []


def test_name_dict_trace():
    """이름 열이 없어 대조 사전이 비면 사유가 남는다 (X18)."""
    skip: list = []
    out, fixes = P.verify_product_names("미래에셋코어텍증권모투자신탁 입니다.",
                                        "mother_fund_names_raw\n미래에셋코어텍증권모투자신탁(주식)", skip)
    assert fixes == [] and skip, (fixes, skip)


# ── 항목 2·3 · KG 부류 A — 구성종목 확정식의 상품명 전파 ─────────────────────────
def _ctx():
    from src.runtime.loader import load_context
    return load_context()


def test_flat_conjuncts_keeps_or_group():
    """괄호 AND 그룹은 평탄화하고, OR 가 든 그룹은 통째로 둔다(의미 보존)."""
    assert P._flat_conjuncts("a = 1 AND (b = 2 AND c = 3)") == ["a = 1", "b = 2", "c = 3"]
    assert P._flat_conjuncts("a = 1 AND (b = 2 OR c = 3)") == ["a = 1", "(b = 2 OR c = 3)"]
    assert P._flat_conjuncts("(a = 1) OR (b = 2)") == ["(a = 1) OR (b = 2)"]      # 겉괄호가 짝이 아니다


def test_holdings_template_keeps_name():
    """기본모수 주입이 원 WHERE 를 괄호로 감싸도 이름 필터가 서브쿼리에 살아남는다 (Z7·AA18)."""
    q = "미래에셋코어테크 펀드가 두 번째로 많이 담은 종목은 뭐야?"
    sql = ("SELECT h.holding_nm, h.weight_pct FROM public_funds p "
           "JOIN ext_fund_holdings h ON h.grp = p.mtco_itm_no AND h.or_co = p.or_co_xtn_itt_cd "
           "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND "
           "(REPLACE(p.itm_nm,' ','') LIKE '%코어테크%' AND h.weight_pct > 0) "
           "ORDER BY h.weight_pct DESC LIMIT 1")
    out, ok = P.ensure_fund_holdings_template(sql, q, _ctx(), "코어테크")
    sub = out[out.index("(SELECT"):]
    assert ok and "코어테크" in sub, out                     # 이름이 **서브쿼리 안에** 있어야 한다
    assert "weight_pct > 0" not in out, out                 # 보유테이블 쪽 무의미 절은 버린다
    assert out.rstrip().endswith("LIMIT 2"), out            # 서수 질의 — 2위까지 실어야 답이 있다(AA18)


def test_holdings_template_refuses_without_fund_pin():
    """펀드를 특정하는 술어가 없으면 확정식을 적용하지 않는다 — 남의 펀드 값보다 오거절이 낫다."""
    q = "펀드가 가장 많이 담은 종목은 뭐야?"
    sql = ("SELECT h.holding_nm FROM public_funds p JOIN ext_fund_holdings h ON h.grp = p.mtco_itm_no "
           "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' ORDER BY h.weight_pct DESC LIMIT 30")
    assert P.ensure_fund_holdings_template(sql, q, _ctx(), None) == (sql, False)


def test_holdings_template_on_etf_leak():
    """라우팅이 public_funds 인데 HCX 가 ETF 테이블로 샜으면 확정식으로 교체한다 (X1·X2·KG-028)."""
    q = "미래에셋코어테크 펀드가 가장 많이 담은 종목 3개 알려줘"
    sql = ("SELECT h.holding_nm, h.weight_pct FROM domestic_etfs e JOIN ext_etf_holdings h "
           "ON h.etf_code = e.pd_itm_no WHERE e.pd_abrv_nm LIKE '%미래에셋 코어테크%' "
           "ORDER BY h.weight_pct DESC LIMIT 3")
    out, ok = P.ensure_fund_holdings_template(sql, q, _ctx(), "코어테크", route_fund=True)
    assert ok and "ext_fund_holdings" in out and "코어테크" in out, out
    # 라우팅이 ETF 면 불개입 — ETF 구성종목 질의를 펀드 템플릿으로 덮지 않는다
    assert P.ensure_fund_holdings_template(sql, q, _ctx(), "코어테크", route_fund=False) == (sql, False)


# ── 항목 7 · 재검 ③-9 부류 B-5′ — 기준일·방법론 날조 문장 제거 ────────────────────
def test_strip_wrong_cutoff():
    """정본과 다른 기준일 주장·집계 방법론 날조·품질 추측만 버리고, 정당한 날짜 문장은 남긴다."""
    from src.runtime import gate
    assert gate.DATA_CUTOFF == "2026-08-24"

    y3 = ("1년 수익률 하위 5개는 다음과 같습니다. "
          "이 데이터는 2026년 8월 21일을 기준으로 한 정보이며, 모든 클래스의 수익률을 합하여 나타낸 내용입니다.")
    out, hit = P.strip_disclaimer(y3)
    assert hit and "8월 21일" not in out and "합하여" not in out, out
    assert "하위 5개는 다음과 같습니다" in out, out

    # 정본 기준일 문장은 남는다 — 기계 조립 머리줄이 매 답변에 굽는 문형이다
    keep = "조회된 공모펀드 1개입니다 (기준일 2026-08-24, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위)."
    assert P.strip_disclaimer(keep) == (keep, False)

    # 설정일·만기일 같은 정당한 날짜 답은 기준 주장 문형이 아니라 건드리지 않는다
    estb = "이 펀드의 설정일은 2011년 3월 22일이며, 약 15년간 운용되고 있습니다."
    assert P.strip_disclaimer(estb) == (estb, False)

    # Y1 — 근거 없는 품질 추측
    y1, hit1 = P.strip_disclaimer("1위는 660.63%입니다. 다만 기준가 산정에 오류가 있을 가능성도 있습니다.")
    assert hit1 and "가능성" not in y1, y1


# ── 항목 9 · KG 부류 B — 확정식 주입은 교체다(같은 축의 잔여 술어 제거) ──────────────
def test_estb_year_replaces_residual():
    """설정연도 확정식은 멱등 재작성이고, 체인 뒤에서 되살아난 잔여 술어를 다시 걷어낸다 (X19)."""
    q = "2025년에 설정된 공모펀드는 몇 개야?"
    # 초기 가드가 지나간 뒤 ensure_ext_join 이 fd_estb_dt → estb_dt 로 이름을 바꿔 잔여가 되살아난 형태
    sql = ("SELECT COUNT(*) FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no "
           "WHERE estb_dt >= '20250101' AND estb_dt < '20260101' AND sale_yn = '판매중' "
           "AND prvo_pbff_desc = '공모' AND estb_dt <= 20250930 LIMIT 30")
    out, ok = P.ensure_fund_estb_year(sql, q)
    assert ok and "20250930" not in out, out
    assert out.count("estb_dt >= '20250101'") == 1 and "estb_dt < '20260101'" in out, out
    assert P.ensure_fund_estb_year(out, q) == (out, False)          # 멱등


def test_series_boundary_drops_other_series():
    """호수 확정식은 질문의 호수뿐 아니라 SQL 의 모든 호수 술어를 걷어낸다 (AA20 거짓 0)."""
    q = "미래에셋차이나솔로몬 시리즈 3호는 클래스가 몇 개야?"
    sql = ("SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
           "AND (REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬%' AND itm_no LIKE '%2호%') LIMIT 30")
    out, ok = P.ensure_fund_series_boundary(sql, q)
    assert ok and "'%2호%'" not in out, out
    assert "미래에셋차이나솔로몬" in out and "[^0-9.]3호*" in out, out     # 이름 필터는 살아남는다
