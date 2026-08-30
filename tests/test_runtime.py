# -*- coding: utf-8 -*-
"""런타임 파이프라인 테스트 — 검증 게이트(BUILD_PLAN §5⑤) 문항이 실제로 기각·매핑되는지.

HCX 없이 전부 오프라인으로 돈다. DB(data/financial_products.db)가 없으면 skip.
"""

import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question, validate_sql

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음 — build_db.py 선행 필요")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


# ── 네거티브 게이트 — HCX 0회 기각 ──────────────────────────────────────

def test_absent_overseas_risk(ctx):
    r = answer_question("T-01", "위험등급 낮은 해외ETF 추천해줘", ctx=ctx)
    assert "hasRiskGrade" in r.think_trace and "[Gate] 기각" in r.think_trace
    assert "제공되지" in r.answer or "확인할 수 없" in r.answer


def test_absent_bond_index(ctx):
    r = answer_question("T-02", "기초지수를 추종하는 채권 알려줘", ctx=ctx)
    assert "[Gate] 기각" in r.think_trace and "tracksIndex" in r.think_trace


def test_enum_crd_aaaa(ctx):
    r = answer_question("T-03", "신용등급 AAAA 채권 있어?", ctx=ctx)
    assert "[Gate] 기각" in r.think_trace and "AAAA" in r.think_trace
    assert "존재하지 않는" in r.answer


def test_enum_crd_valid_not_rejected(ctx):
    # 정상 등급(AAA)은 기각되면 안 된다
    r = answer_question("T-04", "신용등급 AAA 채권 알려줘", ctx=ctx)
    assert "[Gate] 통과" in r.think_trace


def test_risk_grade_out_of_range(ctx):
    r = answer_question("T-05", "위험등급 9등급 펀드 보여줘", ctx=ctx)
    assert "[Gate] 기각" in r.think_trace and "0~6" in r.think_trace


def test_risk_grade_6_valid(ctx):
    # 🔴 규칙 §4 — 6등급은 정상이다 (1~5 제약은 오류). 기각되면 안 된다
    r = answer_question("T-06", "위험등급 6등급 채권 알려줘", ctx=ctx)
    assert "[Gate] 통과" in r.think_trace


def test_cutoff_future(ctx):
    # 🔴 08-30: 연도만 보고 게이트에서 기각하지 않는다 — 플래너가 없으면 해석을 검사할 수 없어 기준일 안내로 끝낸다
    r = answer_question("T-07", "2027년 만기 예정 수익률 전망 알려줘", ctx=ctx)
    assert "[Gate] 기각" not in r.think_trace and "2026-08-22" in r.answer
    assert "사후 판정" in r.think_trace


# ── KG Ground — 표기 매핑 ───────────────────────────────────────────────

def test_ground_org(ctx):
    r = answer_question("T-08", "미래에셋이 운용하는 펀드 알려줘", ctx=ctx)
    assert "or_co_xtn_itt_cd='00080008'" in r.think_trace.replace('"', "'")


def test_ground_index(ctx):
    r = answer_question("T-09", "KOSPI200 추종 상품 알려줘", ctx=ctx)
    assert "Idx_KOSPI200" in r.think_trace


# ── SQL Guard ───────────────────────────────────────────────────────────

def test_sql_guard():
    ok = "SELECT pd_nm FROM domestic_etfs WHERE pd_grp_no='ETF' LIMIT 5"
    assert validate_sql(ok) is None
    assert validate_sql("DELETE FROM domestic_etfs") is not None
    assert validate_sql("SELECT * FROM users LIMIT 5") is not None          # 화이트리스트 밖
    assert validate_sql("SELECT 1 FROM public_funds") is not None           # LIMIT 누락
    assert validate_sql("SELECT 1 FROM public_funds LIMIT 1; DROP TABLE x") is not None


# ── Plan 연결 시 경로 (가짜 planner 로 Execute 까지) ─────────────────────

class FakePlanner:
    def plan_sql(self, question, grounding):
        return "SELECT count(*) AS n FROM domestic_etfs WHERE pd_grp_no='ETF' LIMIT 1"

    def compose_answer(self, question, rows, answer_rules=""):
        return f"조회 결과: {rows.splitlines()[-1]}건"


def test_full_path_with_planner(ctx):
    r = answer_question("T-10", "국내 ETF 몇 개야?", planner=FakePlanner(), ctx=ctx)
    assert "[Execute] 1행 조회" in r.think_trace
    assert "1235" in r.retrieved_context   # ETF 1,235건 — 2차 배포본(2026-08-22) 실측


def test_cutoff_august_allowed(ctx):
    # 기준일 2026-08-22 — 8월은 기준일 포함 월이라 게이트를 통과해야 한다 (2차 데이터 전환 회귀 테스트)
    r = answer_question("T-11", "2026년 8월 상장한 국내 ETF 알려줘", ctx=ctx)
    assert "[Gate] 기각" not in r.think_trace


def test_cutoff_october_rejected(ctx):
    r = answer_question("T-12", "2026년 10월에 상장 예정인 국내 ETF 알려줘", ctx=ctx)
    assert "2026-08-22" in r.answer and "['202610']" in r.think_trace


def test_planner_context_has_rules(ctx):
    txt = ctx.planner_context(["domestic_etfs", "public_funds"])
    assert "## domestic_etfs" in txt and "구매가능" in txt


def test_cross_query_guard_allows_ext_join():
    from src.runtime.pipeline import validate_sql
    ok = "SELECT e.pd_abrv_nm FROM domestic_etfs e JOIN ext_etf_holdings h ON h.etf_code = e.pd_itm_no WHERE h.constituent LIKE '%삼성전자%' LIMIT 10"
    assert validate_sql(ok) is None
    assert validate_sql("SELECT * FROM ext_etf_holdings LIMIT 5") is not None      # 마스터 없이 ext 단독 금지
    assert validate_sql("SELECT * FROM domestic_etfs JOIN sqlite_master LIMIT 5") is not None


def test_cross_query_detected(ctx):
    from src.runtime import gate
    assert gate.is_cross_query("삼성전자를 보유한 국내/해외 ETF와 공모펀드를 연 수익률 기준 TOP10 알려줘", [])
    assert gate.is_cross_query("채권과 ETF 중 뭐가 안전해?", ["domestic_bonds", "domestic_etfs"])
    assert not gate.is_cross_query("KODEX 200 총보수 알려줘", ["domestic_etfs"])


def test_security_grounding_no_false_positive(ctx):
    """삼성전자 ≠ 삼성전기 — Security 노드가 KG 에 있을 때만 검사 (security_auto.yaml 빌드 전이면 skip)."""
    sec = [n for n in ctx.kg_nodes if n.node_type == "Security"]
    if not sec:
        pytest.skip("Security 노드 미빌드 — build_ontology.py 선행 필요")
    r = answer_question("T-20", "삼성전자를 보유한 ETF 알려줘", ctx=ctx)
    assert "'삼성전자'" in r.think_trace and "(Security)" in r.think_trace
    assert "삼성전기" not in r.think_trace


def test_execute_renders_dates_as_int_and_strips_padding():
    """REAL 로 저장된 날짜가 '20271231.0' 으로, 고정폭 pd_nm 이 꼬리 공백째로 답변에 실리던 것 (2026-08-30 밤)."""
    from src.runtime.pipeline import _cell, _execute
    assert _cell(20271231.0, "mat_dt") == "20271231"
    assert _cell(7.123, "applied_yield") == "7.123"
    assert _cell(None, "crd_grd") == ""
    assert _cell("  국고채권 01500-2703  ", "pd_nm") == "국고채권 01500-2703"
    rows, n = _execute("SELECT pd_nm, mat_dt FROM domestic_bonds WHERE mat_dt >= 20260822 LIMIT 3")
    assert n == 3
    for line in rows.splitlines()[1:]:
        name, mat = line.split(" | ")
        assert name == name.strip() and mat.isdigit() and len(mat) == 8
