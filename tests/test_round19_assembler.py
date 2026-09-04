# -*- coding: utf-8 -*-
"""19R 조립기 — 2026-09-04 공모펀드 78문항이 남긴 결함 ②③.

FND-005 한 문항에 세 결함이 겹쳐 있었다(번호 뭉갬 · 클래스수 불일치 · 보수 10배). 원인은 하나였다 —
값 열이 별칭(`as total_commission`)이라 랭킹 기계 조립이 값 자리를 못 찾고 HCX 산문 경로로 떨어진 것.
DOM-10 은 UNION 라벨 가지가 0행이라 헤더만 남았고 답변기가 그 헤더를 세어 "이자형 1개" 를 지어냈다.
"""
import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import (_fee_is_percent, _fee_pct, _order_by_select_pos,
                                  _restore_empty_label_rows, answer_question)

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

FEE_SQL = (
    "SELECT itm_no, TRIM(itm_nm), MIN(or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r) "
    "as total_commission, fd_daily_bas_dt, COUNT(*) AS \"클래스수\" FROM public_funds "
    "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
    "AND (or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r) IS NOT NULL "
    "AND (or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r) > 0 "
    "GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), "
    "printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 "
    "THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY 3 ASC LIMIT 5"
)


class _NoHCX:
    """HCX 를 부르면 그 사실이 답변에 남는다 — 기계 조립이 탔는지 문자열로 판정한다."""

    def plan_sql(self, q, g):
        return FEE_SQL

    def compose_answer(self, q, rows, answer_rules=""):
        return "HCX-CALLED"


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def test_fee_pct_permille_to_percent():
    """보수 4종은 ‰ — 값÷10 이 %. `_pct` 2자리로는 0.0015 가 '0' 으로 뭉개진다."""
    assert _fee_pct(0.015) == "0.0015"
    assert _fee_pct(10.0) == "1"       # 중앙값 10‰ = 1%
    assert _fee_pct(0.4) == "0.04"


def test_fee_conversion_is_idempotent():
    """🔴 환산은 한 번만. 같은 yaml 규칙을 읽은 HCX 가 SQL 에서 이미 ÷10 하면 조립기는 손대지 않는다.

    2026-09-04 서버 실측: `MIN(ROUND((…)/10.0, 4)) AS "총보수_퍼센트"` 위에 조립기가 또 ÷10 해서
    0.0015% 가 0.0002% 로 나갔다(100배). 값이 아니라 **누가 이미 나눴는지**를 봐야 한다."""
    assert _fee_pct(0.0015, already_percent=True) == "0.0015"
    # 별칭이 퍼센트를 말하면 이미 % 다
    assert _fee_is_percent("SELECT a FROM t", "총보수_퍼센트", 0) is True
    # SQL 이 /10 을 했으면 이미 % 다
    div = 'SELECT itm_no, ROUND((or_co_rwrd_r + sale_co_rwrd_r)/10.0, 4) AS x FROM public_funds'
    assert _fee_is_percent(div, "x", 1) is True
    # 원값(‰)이면 아니다
    raw = "SELECT itm_no, MIN(or_co_rwrd_r + sale_co_rwrd_r) as total_commission FROM public_funds"
    assert _fee_is_percent(raw, "total_commission", 1) is False


def test_order_by_position_resolves_alias():
    assert _order_by_select_pos(FEE_SQL) == 2          # ORDER BY 3 → 0-기반 2 = total_commission
    assert _order_by_select_pos("SELECT a, b FROM t ORDER BY a") is None


def test_fee_ranking_is_machine_assembled(ctx):
    """별칭 값열이어도 랭킹 기계 조립이 타야 한다 — HCX 0회."""
    r = answer_question("FND-005", "총보수가 가장 낮은 공모펀드 5개 알려줘", planner=_NoHCX(), ctx=ctx)
    assert "HCX-CALLED" not in (r.answer or ""), "기계 조립이 안 타고 HCX 산문으로 떨어졌다"
    assert "기계 조립" in r.think_trace
    lines = [l for l in (r.answer or "").splitlines() if l[:2] in ("1.", "2.", "3.", "4.", "5.")]
    assert len(lines) == 5, f"번호 목록이 5줄이 아니다: {lines}"
    assert "2.3.4." not in (r.answer or ""), "번호가 뭉개졌다"
    for l in lines:
        assert "클래스" in l, f"항목마다 클래스수를 병기해야 한다: {l}"
    assert "0.0015%" in (r.answer or ""), "‰→% 환산이 안 됐다 (0.015 를 그대로 적으면 10배 오류)"


PCT_SQL = FEE_SQL.replace(
    "MIN(or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r) as total_commission, fd_daily_bas_dt",
    'ROUND((or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r)/10.0, 4) AS "총보수_퍼센트"',
)


class _NoHCXPct(_NoHCX):
    def plan_sql(self, q, g):
        return PCT_SQL


def test_fee_ranking_same_answer_whichever_side_converts(ctx):
    """SQL 이 환산하든 조립기가 환산하든 답은 같아야 한다 — 100배 사고가 난 자리."""
    a = answer_question("FND-005", "총보수가 가장 낮은 공모펀드 5개 알려줘", planner=_NoHCX(), ctx=ctx).answer
    b = answer_question("FND-005", "총보수가 가장 낮은 공모펀드 5개 알려줘", planner=_NoHCXPct(), ctx=ctx).answer
    for ans in (a, b):
        assert "HCX-CALLED" not in (ans or "")
        assert "0.0015%" in (ans or ""), f"환산이 어긋났다: {ans}"


def test_empty_union_label_branch_becomes_zero():
    """0행 가지는 사라지지 않고 0 으로 남는다 — 답변기가 헤더를 세어 지어내던 자리."""
    cols = ["'이자형'", "COUNT(*)"]
    assert _restore_empty_label_rows(cols, [("배당형", 8969)]) == [("배당형", 8969), ("이자형", 0)]
    # 이미 있으면 건드리지 않는다
    both = [("이자형", 12), ("배당형", 8969)]
    assert _restore_empty_label_rows(cols, both) == both
    # COUNT 가 아닌 집계는 0 이 거짓이라 빈칸
    assert _restore_empty_label_rows(["'A'", "AVG(x)"], [("B", 1.5)]) == [("B", 1.5), ("A", None)]
