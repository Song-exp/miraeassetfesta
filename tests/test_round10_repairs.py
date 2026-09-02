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


# ── R1·R2 · 클래스 개수·열거 축은 rptt_ksd_itm_no ────────────────────────────────
def test_r10_lookup_group_rptt():
    """재검 ③-B — mtco 는 398 rptt 그룹에서 클래스 단위로 발급돼 한 펀드를 클래스 수만큼 쪼갠다."""
    s = ("SELECT DISTINCT han_clas_nm, itm_no, TRIM(itm_nm) AS itm_nm FROM public_funds "
         "WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬증권투자신탁%' "
         "AND (REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2호*' OR REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2[([]*') LIMIT 30")
    out, ok = P.ensure_fund_lookup_grouping(s, "미래에셋차이나솔로몬증권투자신탁 2호는 클래스가 몇 개야?")
    assert ok and f"GROUP BY {P._FUND_GROUP_EXPR}" in out
    rows, n = P._execute(out)
    assert n == 1, rows                                     # 7클래스가 한 펀드로 (mtco 축이면 6그룹)
    ans = P._lookup_answer(out, rows, n, None, [])
    assert ans and "클래스 7개" in ans, ans
    # 🔴 랭킹·분포의 모수 집계 축은 그대로 — 정본 펀드 수 3,040 이 흔들리면 R1·T1·V5 가 깨진다
    cnt = P._execute(f"SELECT COUNT(DISTINCT {P._FUND_KEY_EXPR}) FROM public_funds "
                     "WHERE sale_yn='판매중' AND prvo_pbff_desc='공모'")[0]
    assert cnt.splitlines()[1].strip() == "3040", cnt


def test_r10_lookup_class_no_shape():
    """8R 보류 ③-1 — '클래스 몇 개' 불개입은 HCX 의 GROUP BY 유무(모양)를 보지 않는다. 열거 질의는 행 단위."""
    base = ("SELECT itm_no, TRIM(itm_nm) FROM public_funds "
            "WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크증권자투자신탁%' AND sale_yn='판매중' LIMIT 30")
    assert P.ensure_fund_lookup_grouping(base, "미래에셋코어테크 펀드는 클래스가 몇 개야?")[1] is True
    assert P.ensure_fund_lookup_grouping(base, "미래에셋코어테크 펀드는 어떤 클래스들이 있어?")[1] is False
    assert P.ensure_fund_lookup_grouping(base, "미래에셋코어테크 펀드 클래스별 보수 알려줘")[1] is False


def test_r10_lookup_answer_only_for_name_lookup():
    """조립 문형이 "'X' 이름의 …" 이므로 태그 ∪ 이름 목록(KG-021)에는 쓰지 않는다."""
    tag = ("SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS \"클래스수\", "
           "SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS \"판매중클래스수\", "
           "MIN(rptt_ksd_itm_no) AS 대표번호, prfd_attr_cds FROM public_funds "
           "WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' "
           "AND (',' || prfd_attr_cds || ',' LIKE '%,TWN,%' OR REPLACE(itm_nm,' ','') LIKE '%대만%') "
           f"GROUP BY {P._FUND_GROUP_EXPR} LIMIT 30")
    assert P._has_name_filter(tag) is False                 # 태그와 OR 로 묶인 이름 LIKE 는 이름 조회가 아니다
    rows, n = P._execute(tag)
    assert P._lookup_answer(tag, rows, n, None, []) is None


# ── A1 · 접두 앵커 — 이름 리터럴은 「라벨 + 잔여 고유명」 결합형 ───────────────────
def test_r10_name_anchor_prefix():
    """재검 ③-A — or_co 절은 타사만 막는다: 브랜드를 떼면 같은 운용사의 이름 변형이 전부 살아남는다."""
    L = ["'한국투자' → Org_00040024 (Organization) → public_funds.or_co_xtn_itt_cd='00040024'"]
    assert P.residual_name_token("한국투자베트남그로스증권자투자신탁 위험등급 알려줘", L) == "한국투자베트남그로스증권자투자신탁"
    # 결합형이 DB 에 없으면 종전대로 잔여만
    assert P.residual_name_token("한국투자없는이름펀드 위험등급 알려줘", L) == "없는이름펀드"
    # 사용자가 브랜드를 안 썼으면 결합하지 않는다 (S12)
    assert P.residual_name_token("코어테크 펀드 수익률", []) == "코어테크"

    def cnt(lit):
        return int(P._execute("SELECT COUNT(DISTINCT COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), itm_no)) "
                              "FROM public_funds WHERE prvo_pbff_desc='공모' AND TRIM(or_co_xtn_itt_cd)='00040024' "
                              f"AND REPLACE(itm_nm,' ','') LIKE '%{lit}%'")[0].splitlines()[1])
    assert cnt("베트남그로스증권자투자신탁") == 3 and cnt("한국투자베트남그로스증권자투자신탁") == 2


# ── D1 · 표시 열 자릿수 · N8 · 기준일 이후 SQL 리터럴 ────────────────────────────
def test_r10_amount_thousands():
    """재검 ③-6 — 숫자와 단위만 붙여 주면 HCX 가 콤마를 임의 위치에 찍는다(U8 `425,2800백만USD`)."""
    assert P._cell("4378085백만USD", "총순자산_백만USD") == "4,378,085백만USD"
    assert P._cell("12195억원", "순자산_억원") == "12,195억원"
    assert P._cell("3억원", "순자산_억원") == "3억원"            # 4자리 미만은 그대로
    assert P._cell("4,378,085백만USD", "x") == "4,378,085백만USD"   # 멱등


def test_r10_future_date_literal():
    """gold N8 — 기준일 가드가 질문 토큰만 보고 SQL 리터럴은 안 봤다(FND-R02 거짓 사유 거절)."""
    s = ("SELECT itm_nm, fd_mm1_ern_r FROM public_funds WHERE sale_yn='판매중' "
         "AND fd_daily_bas_dt BETWEEN 20260915 AND 20260922 AND fd_mm1_ern_r IS NOT NULL "
         "ORDER BY fd_mm1_ern_r DESC LIMIT 5")
    out, dropped = P.strip_future_basis_date(s)
    assert dropped and "fd_daily_bas_dt" not in out and P._execute(out)[1] == 5
    # 기준일 이내는 사용자 조건 — 손대지 않는다. 만기(mat_dt)는 미래가 정상이라 대상 밖이다.
    keep = "SELECT itm_nm FROM public_funds WHERE fd_daily_bas_dt = 20260824 LIMIT 5"
    assert P.strip_future_basis_date(keep) == (keep, None)
    mat = "SELECT pd_no FROM domestic_bonds WHERE mat_dt <= 20301231 LIMIT 5"
    assert P.strip_future_basis_date(mat) == (mat, None)


# ── I1 · 부정 술어 금지 · H1 · 미조회 축 문장 제거 ───────────────────────────────
def test_r10_no_inverted_predicate():
    """KG 부류 I — Z18: 'ETF로 자산배분하는 공모펀드' 가 NOT LIKE '%ETF%' 로 나가 질문의 정확한 반대."""
    s = ("SELECT itm_no, itm_nm FROM public_funds WHERE zrin_btyp_nm IN ('주식형','해외주식형') "
         "AND REPLACE(itm_nm,' ','') NOT LIKE '%ETF%' AND sale_yn='판매중' AND prvo_pbff_desc='공모' LIMIT 30")
    out, ok = P.fix_inverted_name_predicate(s, "ETF로 자산배분하는 공모펀드 있어?")
    assert ok and "NOT LIKE" not in out and "LIKE '%ETF%'" in out
    # 제외 어휘가 있으면 사용자 조건 — 손대지 않는다 (FND-006 'MMF 제외')
    assert P.fix_inverted_name_predicate(s, "MMF를 제외한 공모펀드 알려줘")[1] is False
    # 질문에 없는 낱말의 NOT LIKE 도 손대지 않는다
    assert P.fix_inverted_name_predicate(s, "주식형 공모펀드 알려줘")[1] is False


def test_r10_unsourced_axis_sentence():
    """KG 부류 E 부수 — AA5: SELECT 에 estb_dt 가 없는데 '설정일 2011-06-20 · 약 12년'."""
    rows = "itm_nm | zrin_fd_ivst_risk_grd_nm\nKB중국본토A주 | 높은 위험"
    out, hit = P.strip_unsourced_estb_claim(
        "KB중국본토A주 펀드는 2011-06-20에 설정되었습니다. 약 12년 운용 중입니다. 위험등급은 2등급입니다.", rows)
    assert hit and "2011" not in out and "12년" not in out and "위험등급은 2등급입니다." in out
    assert "미조회" in out or "확인하지 못했습니다" in out
    # 날짜 축이 결과에 있으면 그대로 둔다 · 설정 축이 아닌 문장도 그대로
    assert P.strip_unsourced_estb_claim("설정일은 2011-06-20입니다.", "itm_nm | estb_dt\nX | 20110620")[1] is False
    assert P.strip_unsourced_estb_claim("이 펀드의 3년 수익률은 12.3%입니다.", rows)[1] is False


# ── T1 · ETF 지수 정본 · S1 · 랭킹 머리줄 조건 ──────────────────────────────────
def test_r10_etf_ref_index():
    """KG 부류 T — cu_base_index 는 95.5% 공백이고 값 있는 9행은 무관 상품. 정본은 ref_base_index."""
    s = ("SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no='ETF' AND pd_sale_yn=1 "
         "AND cu_base_index LIKE '%KOSPI200%' LIMIT 5")
    out, ok = P.ensure_etf_index_canon(s)
    assert ok and "ref_base_index" in out and "cu_base_index" not in out
    assert P._execute(out)[0].splitlines()[1].strip() == "34"          # gold X7 순수추종 34
    assert P.ensure_etf_index_canon(out)[1] is False                   # 멱등
    # 해외 ETF 는 cu_base_index 가 정상이라 대상이 아니다
    ovs = "SELECT COUNT(*) FROM overseas_etfs WHERE cu_base_index LIKE '%S&P500%' LIMIT 5"
    assert P.ensure_etf_index_canon(ovs)[1] is False
    for lit, gold in (("NASDAQ100", "16"), ("S&P500", "24")):          # gold Z19 · AA22
        o2, _ = P.ensure_etf_index_canon(s.replace("KOSPI200", lit))
        assert P._execute(o2)[0].splitlines()[1].strip() == gold, (lit, o2)


def test_r10_rank_head_conditions():
    """gold N3 — 8R 기계 조립이 정렬축·모수만 굽고 WHERE 조건을 안 구워 '매우 낮은 위험' 이 답변에서 사라졌다."""
    sql = ("SELECT itm_no, TRIM(itm_nm) AS itm_nm, MAX(fd_yr1_ern_r) AS fd_yr1_ern_r, COUNT(*) AS \"클래스수\" "
           "FROM public_funds WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
           "AND zrin_fd_ivst_risk_grd_nm='매우 낮은 위험' "
           f"GROUP BY {P._FUND_KEY_EXPR} ORDER BY fd_yr1_ern_r DESC LIMIT 3")
    rows, n = P._execute(sql)
    ans = P._fund_rank_answer(sql, rows, n)
    assert ans and "매우 낮은 위험 기준" in ans.splitlines()[0], ans
    # 모수·식별자 컬럼은 머리줄에 중복해 싣지 않는다
    assert P._rank_filter_labels("SELECT x FROM public_funds WHERE sale_yn='판매중'") == []
