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
