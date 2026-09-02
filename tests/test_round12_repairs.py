"""12라운드 수리 회귀 테스트 — 심사관 셋(§③ 합본)의 처방을 코드로 고정한다.

간섭 지도: docs/recheck_2026-09-03_round12_plan.md
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runtime import pipeline as p                                        # noqa: E402
from runtime.loader import connect_readonly, load_context                # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _ctx():
    ctx = load_context()
    p.set_column_index(ctx.schema)
    return ctx


def _chain_etf(sql: str, question: str) -> str:
    """실 체인의 ETF 두 가드 순서(지수 확정식 → 기본모수·날조 제거)를 그대로 재현한다."""
    sql, _ = p.ensure_etf_index_canon(sql)
    sql, _ = p.ensure_etf_base_population(sql, question)
    return sql


# ── P1 · gold ③-1 — 가드가 주입한 술어는 「날조 술어 제거」의 대상이 아니다 ──
def test_guard_mark_survives_removal():
    """Z19 회귀: 지수 확정식의 영문 리터럴이 한국어 질문에 없다고 지워져 판매중 ETF 전수 1,160 이 나갔다."""
    out = _chain_etf("SELECT COUNT(*) FROM domestic_etfs WHERE cu_base_index LIKE '%NASDAQ100%'",
                     "나스닥100 지수를 추종하는 ETF는 몇 개야?")
    assert "ref_base_index" in out, out
    assert connect_readonly().execute(out).fetchone()[0] == 16, out      # gold: NASDAQ 100 CR 16


def test_removal_never_empties_conditions():
    """gold ③-2 / 1순위 사후조건: 확정식 조건이 증발한 전수 조회를 답으로 내지 않는다."""
    q = "우주항공 관련 ETF 알려줘"
    out = _chain_etf("SELECT pd_abrv_nm FROM domestic_etfs WHERE cu_base_index LIKE '%Aerospace%' "
                     "ORDER BY pd_abrv_nm ASC LIMIT 30", q)
    assert "ref_base_index" in out or "cu_base_index" in out, out
    n = len(connect_readonly().execute(out).fetchall())
    assert n < 30, f"조건이 전소실돼 전수 조회가 됐다: {out}"


def test_chain_restores_lost_canon():
    """체인 끝 사후조건 — 뒤 가드가 확정식을 지웠으면 되돌린다(마커 기반, 가드 무관 일반 규칙)."""
    canon = p.marked_conjuncts(p.ensure_etf_index_canon(
        "SELECT COUNT(*) FROM domestic_etfs WHERE cu_base_index LIKE '%NASDAQ100%'")[0])
    assert canon, "확정식이 표식을 붙이지 않았다"
    stripped = "SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1"
    back, _ = p._append_exclusions(stripped, [c for c in canon if c not in stripped])
    assert "ref_base_index" in back and connect_readonly().execute(back).fetchone()[0] == 16, back


def test_fabricated_predicate_still_removed_when_others_remain():
    """안전망이 종전 제거를 무력화하면 안 된다 — 다른 사용자 조건이 남으면 날조 술어는 그대로 제거된다."""
    sql = ("SELECT SUM(du_last_aum) FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1 "
           "AND cu_charge_rt > 0 AND ref_base_index LIKE '%KOSPI200%'")
    out, changed = p.ensure_etf_base_population(sql, "KOSPI200 ETF 순자산 합계")
    assert changed and "cu_charge_rt" not in out, out


# ── P3 · gold ③-3 — 확정식 치환은 술어 단위가 아니라 비교식 단위다 ──
def test_index_canon_keeps_or_branch():
    """OR 반대편 가지(사용자 조건)까지 버리던 계열 — OFFICIAL-004 이름 가지 소멸."""
    out, ok = p.ensure_etf_index_canon(
        "SELECT pd_abrv_nm FROM domestic_etfs WHERE cu_base_index LIKE '%우주항공%' "
        "OR pd_nm LIKE '%우주항공%' LIMIT 30")
    assert ok and "ref_base_index" in out and "pd_nm LIKE '%우주항공%'" in out, out
    assert p.ensure_etf_index_canon(out)[1] is False, "멱등이 아니다"


def test_index_canon_gold_axes_unchanged():
    """지수 축 gold 는 흔들리지 않는다 — KOSPI200 34 · NASDAQ100 16 (심사관 실측)."""
    con = connect_readonly()
    for lit, gold in (("KOSPI200", 34), ("NASDAQ100", 16)):
        out = _chain_etf(f"SELECT COUNT(*) FROM domestic_etfs WHERE cu_base_index LIKE '%{lit}%'",
                         f"{lit} 지수를 추종하는 ETF는 몇 개야?")
        assert con.execute(out).fetchone()[0] == gold, out


# ── P4 · KG ③-2 (부류 V) — 확정식은 자기 컬럼이 그 FROM 테이블에 있는지 먼저 본다 ──
def test_etf_canon_scope_guard():
    """X8: `FROM public_funds` 문장에 ETF 컬럼을 주입해 스키마 검사가 자기 출력을 기각한 자가 오거절."""
    mixed = ("SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND bmrk_nm LIKE '%S&P500%' "
             "AND itm_no IN (SELECT itm_no FROM domestic_etfs WHERE cu_base_index LIKE '%S&P500%')")
    assert p.ensure_etf_index_canon(mixed)[1] is False, "테이블이 섞인 문장에 확정식이 개입했다"
    assert p.ensure_etf_base_population(mixed, "S&P500 공모펀드 몇 개")[1] is False


# ── P5 · 재검 ③-4 (부류 AB) — 랭킹의 묶기 축은 대표예탁원번호다 ──
def test_rank_axis_is_rptt():
    """mtco 는 398 rptt 그룹에서 클래스 단위로 발급돼 한 펀드를 쪼갠다(Y4 1위 '클래스 1개'인데 실제 9)."""
    s = ("SELECT itm_no, TRIM(itm_nm), fd_yr3_ern_r FROM public_funds "
         "WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' ORDER BY fd_yr3_ern_r DESC LIMIT 5")
    s, _ = p.ensure_fund_return_error_exclusion(s)            # 실 체인 순서(기점오류 3클래스 제외)
    out, ok = p.ensure_fund_rank_representative(s, "3년 수익률이 가장 높은 공모펀드 5개")
    assert ok and f"GROUP BY {p._FUND_GROUP_EXPR}" in out, out
    assert p.ensure_fund_rank_representative(out, "3년 수익률이 가장 높은 공모펀드 5개")[1] is False

    # 심사관 §③-4 실측: 4위 NH-Amundi 1.5배 417.77(5클래스) · 5위 미래에셋차세대Fun 294.63(1)
    rows, n = p._execute(out)
    body = [ln.split(" | ") for ln in rows.splitlines()[1:]]
    assert [r[2] for r in body][3:] == ["417.77", "294.63"], rows

    # 🔴 모수 집계 축(3,040)은 안 움직인다 — R1·T1·V5 는 펀드 단위 GROUP BY 를 쓰지 않는다
    con = connect_readonly()
    assert con.execute(f"SELECT COUNT(DISTINCT {p._FUND_KEY_EXPR}) FROM public_funds "
                       "WHERE sale_yn='판매중' AND prvo_pbff_desc='공모'").fetchone()[0] == 3040


def test_rank_axis_respects_list_grouping():
    """목록 묶기가 만든 정본 축은 다시 갈지 않는다 — 갈면 목록 조립기가 꺼져 커버리지 고지가 사라진다."""
    listed = ("SELECT itm_no, itm_nm, COUNT(*) AS \"클래스수\", MAX(fd_nast_suma) AS fd_nast_suma "
              "FROM public_funds WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
              f"GROUP BY {p._FUND_KEY_EXPR} ORDER BY fd_nast_suma DESC LIMIT 30")
    out, _ = p.ensure_fund_rank_representative(listed, "순자산이 큰 공모펀드 알려줘")
    assert f"GROUP BY {p._FUND_KEY_EXPR}" in out, out


# ── P6 · KG ③-4 (부류 T-2) — ETF 운용사 축은 ref_fund_mgmt_co 정확일치 ──
def test_etf_mgmt_canon_240():
    """🔴 접두 LIKE 금지 — Samsung Active Asset Management 25행은 별개 법인이다(265 = 240 + 25)."""
    con = connect_readonly()
    base = " AND pd_grp_no='ETF' AND pd_sale_yn=1"
    for pred in ("cu_fund_mgmt_co = '삼성'",
                 "cu_fund_mgmt_co IN ('삼성','Samsung Asset Management Co Ltd')",
                 "cu_fund_mgmt_co LIKE '%삼성%'"):
        out, ok = p.ensure_etf_mgmt_canon(f"SELECT COUNT(*) FROM domestic_etfs WHERE {pred}{base}")
        assert ok and "ref_fund_mgmt_co = 'Samsung Asset Management Co Ltd'" in out, out
        assert con.execute(out).fetchone()[0] == 240, out                       # gold
    # 매핑을 못 만들면 아무것도 지우지 않는다 (확정식 원자성)
    unk = "SELECT COUNT(*) FROM domestic_etfs WHERE cu_fund_mgmt_co = '없는이름xyz'"
    assert p.ensure_etf_mgmt_canon(unk) == (unk, False)


def test_ground_drops_contaminated_slot():
    """AA21 뿌리 — 오염·정본 슬롯을 한 줄에 나란히 실어 HCX 가 섞었다. 정본이 있으면 오염은 싣지 않는다."""
    aliases = [("domestic_etfs", "cu_fund_mgmt_co", "삼성"),
               ("domestic_etfs", "ref_fund_mgmt_co", "Samsung Asset Management Co Ltd"),
               ("domestic_etfs", "cu_strtegy", "패시브")]
    kept = p._drop_contaminated_slots(aliases)
    assert [a[1] for a in kept] == ["ref_fund_mgmt_co", "cu_strtegy"], kept     # 짝 없는 cu_* 는 남는다


# ── P7 · gold ③-12 (부류 W) — 클래스 축 집계는 SUM 이 아니라 MAX/MIN ──
def test_class_axis_sum_replaced():
    """FND-005: SUM(보수4합)이 클래스 11개짜리 펀드 보수를 11배로 부풀려 top5 밖으로 밀었다."""
    s = ("SELECT itm_no, TRIM(itm_nm) AS itm_nm, "
         "SUM(or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r) AS 총보수 "
         "FROM public_funds WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
         "GROUP BY or_co_xtn_itt_cd, mtco_itm_no ORDER BY 3 ASC LIMIT 5")
    out, ok = p.ensure_fund_rank_representative(s, "총보수가 가장 낮은 공모펀드 5개")
    assert ok and "MIN(or_co_rwrd_r +" in out and "SUM(" not in out, out
    assert p.ensure_fund_rank_representative(out, "총보수가 가장 낮은 공모펀드 5개")[1] is False

    # 🔴 순자산만 SUM 축을 허용한다 — 이 DB 의 fd_nast_suma 는 클래스별 값이라 펀드 순자산은 합계다
    nast = ("SELECT itm_no, TRIM(itm_nm) AS itm_nm, SUM(fd_nast_suma) AS fd_nast_suma "
            "FROM public_funds WHERE sale_yn='판매중' "
            "GROUP BY or_co_xtn_itt_cd, mtco_itm_no ORDER BY 3 DESC LIMIT 5")
    out2, _ = p.ensure_fund_rank_representative(nast, "순자산이 가장 큰 펀드 5개")
    assert "SUM(fd_nast_suma)" in out2, out2


# ── P9 · 재검 ③-1 (부류 AA) — 조립 발동 판정에서 식별 컬럼도 잡음이다 ──
def test_lookup_class_only_ignores_id_cols():
    """V12 회귀: SELECT 에 섞인 MAX(mtco_itm_no) 하나로 클래스 개수 조립기가 꺼졌다."""
    sql = ("SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS \"클래스수\", "
           "SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS \"판매중클래스수\", "
           "MAX(mtco_itm_no) AS mtco_itm_no, MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds "
           "WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬%' "
           f"GROUP BY {p._FUND_GROUP_EXPR} LIMIT 30")
    rows, n = p._execute(sql)
    ans = p._lookup_answer(sql, rows, n, "미래에셋차이나솔로몬", [])
    assert ans and ans.count("\n- ") == n, ans        # 받은 행이 전부 답변에 실린다
    assert "클래스 7개" in ans and "클래스 8개" in ans, ans


# ── P10 · 재검 ③-3 (부류 V′) — 랭킹 축 판정에서 기본모수 컬럼은 뺀다 ──
def test_rank_axis_ignores_base_population_cols():
    """U14: 축이 {or_co_xtn_itt_cd, prvo_pbff_desc} 라 정본 교체를 못 하고 무음 종료했다.

    심사관 gold: 한화2.2배 6 · NH-Amundi코리아2배 4 · 삼성KOSPI200 제1호 7.
    """
    s = ("SELECT itm_no, TRIM(itm_nm) AS itm_nm FROM public_funds "
         "WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
         "GROUP BY or_co_xtn_itt_cd, prvo_pbff_desc ORDER BY SUM(fd_yr1_ern_r) DESC LIMIT 3")
    s, _ = p.ensure_fund_return_error_exclusion(s)
    out, ok = p.ensure_fund_rank_representative(s, "1년 수익률이 가장 높은 공모펀드 3개")
    assert ok and f"GROUP BY {p._FUND_GROUP_EXPR}" in out and "SUM(" not in out, out
    body = [ln.split(" | ") for ln in p._execute(out)[0].splitlines()[1:]]
    assert [r[2] for r in body] == ["387.66", "362.53", "361.3"], body
    assert [r[3] for r in body] == ["6", "4", "7"], body


# ── P11 · 재검 ③-10·③-6 — 억원 병기도 「불일치 시 교체」 · 표시는 전부 ROUND ──
def test_eok_display_replaced_on_mismatch():
    """부류 Z 잔존: 「표시 열이 이미 있으면 불개입」이라 HCX 가 분모를 틀리면 가드가 자기를 껐다(9R U2·Y7)."""
    wrong = ("SELECT itm_nm, fd_nast_suma, CAST(fd_nast_suma/1000000 AS INTEGER) || '억원' AS \"순자산_억원\" "
             "FROM public_funds LIMIT 5")
    out, ok = p.ensure_amount_eok_columns(wrong)
    assert ok and "/1000000 " not in out and "CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER)" in out, out
    assert p.ensure_amount_eok_columns(out)[1] is False, "멱등이 아니다"

    # 분모·단위가 확정식과 같으면 종전대로 불개입
    right = out
    assert p.ensure_amount_eok_columns(right)[1] is False


def test_eok_rounding_is_consistent_across_paths():
    """③-6: 같은 금액을 T3 은 331,098(ROUND) · T2·V5 는 331,097(절사)로 적었다 — 경로 무관 ROUND."""
    con = connect_readonly()
    total = con.execute("SELECT SUM(fd_nast_suma) FROM public_funds WHERE sale_yn='판매중' "
                        "AND prvo_pbff_desc='공모' AND or_co_xtn_itt_cd='00040010'").fetchone()[0]
    bare, _ = p.ensure_amount_eok_columns("SELECT fd_nast_suma FROM public_funds LIMIT 1")
    assert "ROUND(" in bare, bare
    agg, _ = p.ensure_amount_eok_columns("SELECT SUM(fd_nast_suma) FROM public_funds LIMIT 1")
    assert "ROUND(" in agg, agg
    assert round(total / 100000000) == int(con.execute(
        "SELECT CAST(ROUND(SUM(fd_nast_suma)/100000000.0) AS INTEGER) FROM public_funds "
        "WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' AND or_co_xtn_itt_cd='00040010'").fetchone()[0])


# ── P12 · gold ③-8 (부류 Y) — 결과 전사는 사람이 읽는 표로 낸다 ──
def test_rows_answered_uses_ko_labels():
    """FND-R03·OFFICIAL-005: `TRIM(itm_nm)`·`cu_lev_fector`·`fd_price_bas_dt` 가 사용자 화면에 나갔다."""
    rows = ("TRIM(itm_nm) | itm_no | fd_yr1_ern_r | or_co_xtn_itt_cd | 순자산_억원\n"
            "미래에셋코어테크 | KR1234 | 17.41 | 00080008 | 1,234억원")
    out, ok = p.ensure_rows_answered("조회 결과에 해당 정보가 포함되어 있지 않습니다.", rows, 1)
    assert ok, out
    for raw in ("TRIM(itm_nm)", "itm_no", "or_co_xtn_itt_cd", "fd_yr1_ern_r", "KR1234", "00080008"):
        assert raw not in out, (raw, out)
    assert "종목명 미래에셋코어테크" in out and "17.41" in out and "1,234억원" in out, out

    # 테이블 무관 — ETF 컬럼도 스키마 한글명으로 (하드코딩 0)
    out2, _ = p.ensure_rows_answered("알 수 없습니다.",
                                     "cu_lev_fector | pd_nm\n2.0 | KODEX 레버리지", 1)
    assert "cu_lev_fector" not in out2 and "배수 2.0" in out2, out2

    # 값을 하나라도 인용한 부분 유보는 불개입(종전 규칙)
    assert p.ensure_rows_answered("17.41% 는 확인되나 나머지는 알 수 없습니다.", rows, 1)[1] is False


# ── P13 · 재검 ③-9 · KG ③-16 · gold ③-20 — 금지 문형은 어휘가 아니라 문형으로 ──
def test_disclaimer_covers_recommend_form():
    """U9 '권장합니다' · X13 '참고용으로만' · OFFICIAL-003 '유용한 정보를 제공' 이 사전을 빠져나갔다."""
    for text, gone in (
            ("3년 수익률은 17.4%입니다. 투자 결정 전에 추가 정보를 확인하는 것을 권장합니다.", "권장"),
            ("분포는 다음과 같습니다. 이 결과는 참고용으로만 활용하시기 바랍니다.", "참고용"),
            ("조회 결과입니다. 우주항공 ETF는 유용한 정보를 제공할 것입니다.", "유용한")):
        out, ok = p.strip_disclaimer(text)
        assert ok and gone not in out and out.split(".")[0] in text, out

    # 🔴 데이터에서 나온 주의 문구·값 문장은 대상이 아니다
    for keep in ("수익률 8기간 컬럼은 모두 누적 수익률이며 연 환산이 아닙니다.",
                 "설정일 2019-10-21 (약 6년 10개월).",
                 "위험등급 6등급(매우 낮은 위험)입니다."):
        assert p.strip_disclaimer(keep) == (keep, False), keep


# ── KG ③-10 (부류 D·G) — 개체 개수 랭킹의 정렬 축은 COUNT(DISTINCT 펀드키) ──
def test_entity_count_ranking_axis():
    """KG-008: 개수 질문인데 SUM(fd_nast_suma) 정렬 + COUNT(*)(클래스수)를 '257개의 펀드'로 명시했다."""
    s = ("SELECT trim(trusc_xtn_itt_cd) as 수탁회사명, SUM(fd_nast_suma) as 수탁금액 FROM public_funds "
         "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY 1 ORDER BY 2 DESC LIMIT 3")
    out, ok = p.ensure_fund_entity_count_ranking(s, "공모펀드를 가장 많이 수탁하는 수탁사 상위 3개 알려줘")
    assert ok and '"펀드수"' in out and '"클래스수"' in out and 'ORDER BY "펀드수" DESC' in out, out
    body = [ln.split(" | ") for ln in p._execute(out)[0].splitlines()[1:]]
    assert [r[-2] for r in body] == ["714", "516", "465"], body      # gold 펀드수 축
    assert [r[-1] for r in body] == ["1827", "1656", "1466"], body   # 클래스수는 구분해 병기
    assert p.ensure_fund_entity_count_ranking(out, "공모펀드를 가장 많이 수탁하는 수탁사 상위 3개 알려줘")[1] is False

    # 금액 축 질의·펀드 식별 축은 불개입(랭킹 가드·운용사 템플릿 담당)
    assert p.ensure_fund_entity_count_ranking(s, "순자산이 가장 많은 수탁사 3개")[1] is False
    fund_axis = ("SELECT itm_no, COUNT(*) FROM public_funds GROUP BY itm_no ORDER BY 2 DESC LIMIT 3")
    assert p.ensure_fund_entity_count_ranking(fund_axis, "가장 많은 펀드 3개")[1] is False
