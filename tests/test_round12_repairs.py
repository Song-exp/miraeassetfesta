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
