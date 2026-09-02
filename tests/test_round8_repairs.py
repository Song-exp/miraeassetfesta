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
