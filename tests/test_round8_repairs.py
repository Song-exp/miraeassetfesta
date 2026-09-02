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


# ── 항목 10 · 재검 ③-4 부류 B-4″ — 금액 표시 열을 통화까지 포함해 전 테이블로 ────────
def test_overseas_amount_display_unit():
    """해외 ETF 순자산도 사람이 읽는 표시 열을 받고, 통화는 DB 실측이다 (Y16 10배 과대 · U8 '원' 오표기)."""
    y16 = ("SELECT cu_fund_mgmt_co AS 운용사, SUM(du_last_aum) AS 총순자산USD FROM overseas_etfs "
           "WHERE pd_grp_no='ETF' AND pd_sale_yn=1 GROUP BY 1 ORDER BY 2 DESC LIMIT 3")
    out, ok = P.ensure_amount_eok_columns(y16)
    assert ok and "백만USD" in out and "/1000000.0" in out, out
    assert P.ensure_amount_eok_columns(out) == (out, False)                 # 멱등

    rows = ("운용사 | 총순자산USD | 총순자산USD_백만USD\n"
            "BlackRock Fund Advisors | 4380604640000 | 4380605백만USD")
    kept, hidden = P._hide_answer_columns(rows, out)
    assert hidden == ["총순자산USD"], hidden                                  # 표시 열이 붙었으니 원값을 숨긴다
    assert "4380605백만USD" in kept and "4380604640000" not in kept, kept

    # 원화 경로는 종전 그대로 — 억원
    dom = "SELECT cu_fund_mgmt_co, SUM(du_last_aum) as total_aum FROM domestic_etfs GROUP BY 1 LIMIT 3"
    assert "억원" in P.ensure_amount_eok_columns(dom)[0]
    assert "억원" in P.ensure_amount_eok_columns("SELECT itm_nm, fd_nast_suma FROM public_funds LIMIT 5")[0]


# ── 항목 11 · KG 부류 F / 재검 ③-5 — 기본모수의 반쪽 주입 ────────────────────────
def test_offshore_is_not_a_sale_axis_widener():
    """'역외' 는 운용사 코드 집합을 넓히는 말이지 판매상태를 넓히는 말이 아니다 (KG-031 167/350 → gold 153/293)."""
    q = "피델리티가 운용하는 공모펀드는 역외펀드까지 포함하면 몇 개야?"
    sql = ("SELECT COUNT(*) FROM public_funds WHERE or_co_xtn_itt_cd IN ('00080029','00130001') "
           "AND prvo_pbff_desc = '공모'")
    out, ok = P.ensure_fund_base_population(sql, q)
    assert ok and "sale_yn = '판매중'" in out, out
    # 판매상태·공모여부를 실제로 넓히는 말은 종전대로 존중한다
    assert P.ensure_fund_base_population("SELECT COUNT(*) FROM public_funds WHERE prvo_pbff_desc='사모'",
                                         "한국투자신탁운용 사모펀드는 몇 개야?")[1] is False
    assert P.ensure_fund_base_population("SELECT COUNT(*) FROM public_funds WHERE sale_yn='판매완료'",
                                         "판매완료 펀드는 몇 개야?")[1] is False


def test_etf_base_population_injected():
    """ETF 랭킹·집계에 상품군 확정식(pd_grp_no='ETF' · pd_sale_yn=1)을 주입한다 (U8 모수 날조 · AA22 49 vs 45)."""
    aa22 = "SELECT COUNT(*) FROM domestic_etfs WHERE ref_base_index LIKE '%S&P 500%'"
    out, ok = P.ensure_etf_base_population(aa22, "S&P500 추종 국내 ETF는 몇 개야?")
    assert ok and "pd_grp_no = 'ETF'" in out and "pd_sale_yn = 1" in out, out
    assert P.ensure_etf_base_population(out, "S&P500 추종 국내 ETF는 몇 개야?") == (out, False)   # 멱등

    # 이미 있는 절은 다시 넣지 않는다
    u8 = ("SELECT cu_fund_mgmt_co, SUM(du_last_aum) FROM overseas_etfs WHERE pd_sale_yn=1 "
          "GROUP BY 1 ORDER BY 2 DESC LIMIT 5")
    out2, _ = P.ensure_etf_base_population(u8, "해외 ETF 순자산 상위 5개 운용사 알려줘")
    assert out2.count("pd_sale_yn") == 1 and "pd_grp_no = 'ETF'" in out2, out2

    # ETN 질의는 상품군 확정식을 붙이지 않는다(주최 규칙의 ETF/ETN 분리를 거꾸로 적용하지 않는다)
    etn, _ = P.ensure_etf_base_population("SELECT COUNT(*) FROM domestic_etfs ORDER BY 1", "국내 ETN 몇 개야?")
    assert "pd_grp_no" not in etn, etn

    # 랭킹·집계 꼴이 아니면 불개입
    plain = "SELECT pd_nm FROM domestic_etfs LIMIT 5"
    assert P.ensure_etf_base_population(plain, "국내 ETF 알려줘") == (plain, False)


# ── 항목 8 · 재검 ③-10 부류 F6″-b — 랭킹 답변 기계 조립 ──────────────────────────
RANK_SQL = ('SELECT itm_no, TRIM(itm_nm), MAX(fd_yr1_ern_r) AS fd_yr1_ern_r, COUNT(*) AS "클래스수" '
            "FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
            "GROUP BY " + P._FUND_KEY_EXPR + " ORDER BY fd_yr1_ern_r DESC LIMIT 2")


def test_rank_answer_assembles():
    """클래스수를 반드시 옮기고, 값 축(MAX/MIN)을 머리줄에 굽고, 이름은 클래스 접미를 뗀 펀드명이다."""
    rows = ("itm_no | TRIM(itm_nm) | fd_yr1_ern_r | 클래스수\n"
            "KR1 | 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형) 종류Ce | 387.66 | 6\n"
            "KR2 | NH-Amundi코리아2배레버리지증권투자신탁[주식-파생형] Class Ae | 362.53 | 4")
    out = P._fund_rank_answer(RANK_SQL, rows, 2)
    assert out and "클래스 6개" in out and "클래스 4개" in out, out
    assert "1년 수익률 상위 2개 공모펀드" in out and "클래스 최고값(MAX)" in out, out
    assert "판매중·공모 기준" in out and "기준일 2026-08-24" in out, out
    assert "종류Ce" not in out and "Class Ae" not in out, out          # 클래스명이 아니라 펀드명
    assert "누적 수익률" in out, out                                    # 100% 초과 — 수익률극단값 규칙의 주의 문구

    # 하위 랭킹은 MIN 축으로 고지한다
    low = P._fund_rank_answer(RANK_SQL.replace("DESC", "ASC").replace("MAX(", "MIN("),
                              rows.replace("387.66", "-83.96").replace("362.53", "-79.07"), 2)
    assert low and "하위 2개" in low and "클래스 최저값(MIN)" in low and "누적 수익률" not in low, low


def test_rank_answer_skips_without_class_count():
    """클래스수가 SELECT 에 없으면 조립하지 않는다 — 재료 없이 지어내지 않는다(V16·Y1·Y5 는 HCX 경로 유지)."""
    sql = RANK_SQL.replace(', COUNT(*) AS "클래스수"', "")
    rows = "itm_no | TRIM(itm_nm) | fd_yr1_ern_r\nKR1 | 어떤펀드 | 387.66"
    assert P._fund_rank_answer(sql, rows, 1) is None
    # GROUP BY 펀드키가 없어도 조립하지 않는다(클래스 단위 행이라 '펀드 상위 N' 이 거짓이 된다)
    assert P._fund_rank_answer(RANK_SQL.replace("GROUP BY " + P._FUND_KEY_EXPR, "GROUP BY itm_no"),
                               "itm_no | TRIM(itm_nm) | fd_yr1_ern_r | 클래스수\nKR1 | 펀드 | 1.0 | 1", 1) is None
