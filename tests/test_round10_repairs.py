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


# ── Z1 · 확정식 가드는 「절이 없는가」가 아니라 「절이 확정식인가」를 본다 ────────────
def test_r10_guard_replaces_wrong_clause():
    """9R 회귀 Y7·U8 — HCX 가 절을 **틀리게** 쓰면 종전 가드는 자기를 껐다."""
    # ⓐ 유형 축: `IN ('주식형','해외주식형')` 는 질문의 정확 일치 값 하나로 축소된다 (③-4)
    base = ("SELECT e.mgmt_co_nm, SUM(p.fd_nast_suma) AS total FROM public_funds p "
            "LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no "
            "WHERE p.zrin_btyp_nm IN ('주식형','해외주식형') GROUP BY 1 ORDER BY 2 DESC LIMIT 3")
    out, ok = P.ensure_fund_type_axis(base, "주식형 펀드 순자산이 가장 큰 운용사 3곳 알려줘")
    assert ok and "p.zrin_btyp_nm = '주식형'" in out and "해외주식형" not in out
    assert P.ensure_fund_type_axis(out, "주식형 펀드 순자산이 가장 큰 운용사 3곳 알려줘")[1] is False   # 멱등
    # 총칭어(열거값 없음)·약관분류 축은 불개입
    assert P.ensure_fund_type_axis(base, "채권 펀드 순자산이 가장 큰 운용사")[1] is False

    # ⓑ ETF 모수: 뒤집힌 값은 확정식으로 교체되고, 질문에 근거 없는 술어는 걷힌다 (③-5)
    etf = ("SELECT cu_fund_mgmt_co, SUM(du_last_aum) AS t FROM overseas_etfs "
           "WHERE pd_sale_yn IN (0,1) AND cu_charge_rt > 0 GROUP BY 1 ORDER BY 2 DESC LIMIT 5")
    out2, ok2 = P.ensure_etf_base_population(etf, "순자산 합계가 가장 큰 해외 ETF 운용사 5곳")
    assert ok2 and "pd_sale_yn = 1" in out2 and "cu_charge_rt" not in out2 and "pd_grp_no = 'ETF'" in out2
    # 질문이 보수를 물으면 그 술어는 사용자 조건이다 — 남긴다
    out3, _ = P.ensure_etf_base_population(etf, "총보수가 있는 해외 ETF 운용사 순자산 5곳")
    assert "cu_charge_rt > 0" in out3


def test_r10_rank_group_axis_canonical():
    """gold ③-B 6 + 재검 ③-3 — HCX 자작 펀드키는 정본식으로 교체하고 클래스수를 병기한다."""
    s = ("SELECT itm_no, TRIM(itm_nm), fd_yr1_ern_r FROM public_funds "
         "WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
         "GROUP BY or_co_xtn_itt_cd, mtco_itm_no ORDER BY fd_yr1_ern_r DESC LIMIT 3")
    out, ok = P.ensure_fund_rank_representative(s, "1년 수익률이 가장 높은 공모펀드 3개")
    assert ok and f"GROUP BY {P._FUND_KEY_EXPR}" in out and '"클래스수"' in out
    assert P.ensure_fund_rank_representative(out, "1년 수익률이 가장 높은 공모펀드 3개")[1] is False
    # 분포 축(유형별)은 답의 축이라 교체하지 않는다
    dist = "SELECT zrin_btyp_nm, fd_yr1_ern_r FROM public_funds GROUP BY zrin_btyp_nm ORDER BY 2 DESC LIMIT 5"
    assert P.ensure_fund_rank_representative(dist, "유형별 1년 수익률")[1] is False


def test_r10_class_count_off_value_predicate():
    """재검 ③-2 / KG 부류 S — 클래스수는 값 술어 **밖**에서 센다. 값·순서는 안 바뀐다."""
    s = ("SELECT itm_no, TRIM(itm_nm) AS itm_nm, fd_yr3_ern_r FROM public_funds "
         "WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
         "AND fd_yr3_ern_r IS NOT NULL AND fd_yr3_ern_r < 0 ORDER BY fd_yr3_ern_r ASC LIMIT 5")
    out, ok = P.ensure_fund_rank_representative(s, "3년 수익률이 가장 낮은 공모펀드 5개")
    assert ok and "HAVING MIN(fd_yr3_ern_r)" in out and "AND fd_yr3_ern_r <" not in out
    new = [ln.split(" | ") for ln in P._execute(out)[0].splitlines()[1:]]
    old_sql = (s.replace(" ORDER BY", f" GROUP BY {P._FUND_KEY_EXPR} ORDER BY")
                .replace("fd_yr3_ern_r FROM", "MIN(fd_yr3_ern_r) AS fd_yr3_ern_r, COUNT(*) AS k FROM"))
    old = [ln.split(" | ") for ln in P._execute(old_sql)[0].splitlines()[1:]]
    assert [r[2] for r in new] == [r[2] for r in old]          # 값·순서 불변
    assert [r[3] for r in new] != [r[3] for r in old]          # 클래스수만 전체 모수로
    # 방향이 안 맞는 술어(DESC 에 `< 0`)는 옮기지 않는다 — 대표값이 달라진다
    desc = s.replace("ORDER BY fd_yr3_ern_r ASC", "ORDER BY fd_yr3_ern_r DESC")
    assert "HAVING MAX(fd_yr3_ern_r) <" not in P.ensure_fund_rank_representative(desc, "3년 수익률 상위")[0]
