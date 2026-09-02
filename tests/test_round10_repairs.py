# -*- coding: utf-8 -*-
"""10R 수리 회귀 — docs/recheck_2026-09-03_round10_plan.md 항목별.

각 테스트 = 계획표 (b) 열에 적은 이름. 실패하면 그 항목의 일반 규칙이 깨진 것이다.
"""
import pytest

from src.runtime import guard as G
from src.runtime import pipeline as P
from src.runtime.loader import db_path, load_context

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


# ── N1 · 최상위 OR/AND 혼용은 기각이 아니라 보정 ────────────────────────────────
FND009_SQL = ("SELECT itm_no, SUM(fd_nast_suma) AS s FROM public_funds "
              "WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
              "AND zrin_btyp_nm IN ('주식형','해외주식형') "
              "OR (zrin_btyp_nm IS NULL AND (itm_nm LIKE '%주식%')) "
              "AND fd_nast_suma IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 5")


def test_r10_or_group_parens():
    """OR 는 AND 보다 강하게 묶인다 — 기각 대신 재괄호화하고, 그 결과가 validate_sql 을 통과한다."""
    assert P.validate_sql(FND009_SQL), "전제: 8R 괄호 가드가 이 문장을 기각한다"
    fixed, changed = P.ensure_or_group_parens(FND009_SQL)
    assert changed and P.validate_sql(fixed) is None, fixed
    assert "AND (zrin_btyp_nm IN ('주식형','해외주식형') OR (" in fixed, fixed
    assert P.ensure_or_group_parens(fixed)[1] is False                 # 멱등

    # 괄호가 이미 있는 의도적 형태는 뒤집지 않는다
    ok = ("SELECT 1 FROM public_funds WHERE (sale_yn='판매중' AND prvo_pbff_desc='공모') "
          "OR (sale_yn='판매완료' AND prvo_pbff_desc='사모') LIMIT 1")
    assert P.ensure_or_group_parens(ok)[1] is False


# ── Q1 · UNION 가지 · 서브쿼리는 독립 스코프 ────────────────────────────────────
X8_SQL = ("SELECT '공모펀드' AS 구분, COUNT(*) AS n FROM public_funds "
          "WHERE prvo_pbff_desc='공모' AND bmrk_nm LIKE '%S&P500%' "
          "UNION ALL SELECT '국내 ETF', COUNT(*) FROM domestic_etfs "
          "WHERE pd_grp_no='ETF' AND ref_base_index LIKE '%S&P 500%' LIMIT 2")
SUB_SQL = ("SELECT e.estb_dt FROM ext_fund_page e "
           "WHERE itm_no IN (SELECT itm_no FROM public_funds WHERE sale_yn='판매중') LIMIT 5")


def test_r10_scope_split_no_false_reject():
    ctx = load_context()
    # ⓐ UNION 둘째 가지의 SELECT COUNT(*) 를 첫 가지 WHERE 로 읽지 않는다
    assert P.where_window_or_aggregate(X8_SQL) is None
    # ⓑ 서브쿼리는 스코프가 갈려 itm_no 가 모호하지 않다
    assert G.ambiguous_columns(SUB_SQL, ctx) == []
    # ⓒ 진짜 모호(같은 스코프의 JOIN)는 그대로 잡는다
    joined = ("SELECT itm_no, estb_dt FROM public_funds p "
              "LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no LIMIT 5")
    assert "itm_no" in G.ambiguous_columns(joined, ctx)
    # ⓓ WHERE 안의 진짜 집계는 여전히 기각 사유다
    agg = "SELECT itm_no FROM public_funds WHERE COUNT(*) > 3 LIMIT 5"
    assert P.where_window_or_aggregate(agg)


# ── N2 · 가드는 위반을 전부 모아 한 번에 돌려준다 ───────────────────────────────
def test_r10_precheck_collects_all():
    ctx = load_context()
    # 괄호 위반 + FROM/JOIN 에 없는 테이블 참조 — 8R 은 첫 사유만 돌려줘 재생성 예산 1회가 둘로 쪼개졌다
    bad = ("SELECT pd_nm FROM domestic_etfs WHERE pd_grp_no='ETF' AND cu_charge_rt>0 "
           "OR ext_etf_holdings.ticker='LI' AND pd_sale_yn=1 LIMIT 5")
    err = P._sql_precheck(bad, ctx, ["domestic_etfs"], False)
    assert err and "ext_etf_holdings" in err, err
