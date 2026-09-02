# -*- coding: utf-8 -*-
"""2026-08-30 개선 R-1·R-2·R-4·R-5·R-9 — HCX 없이 전부 오프라인으로 돈다.

근거: docs/research/온톨로지_개정안_2026-08-30.md · 개선_구현_및_기대효과_2026-08-30.md
"""
import time

import pytest

from src.hcx.planner import _SQL_SYSTEM, extract_refuse
from src.runtime import gate, guard
from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import REFUSE_PREFIX, answer_question, build_grounding

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


class SeqPlanner:
    """plan_sql 호출마다 다음 SQL 을 낸다 — 재생성 경로 검증용. HCX 호출 0회."""

    def __init__(self, *sqls):
        self.sqls = list(sqls)
        self.calls = 0
        self.groundings = []

    def plan_sql(self, question, grounding):
        self.groundings.append(grounding)
        self.calls += 1
        return self.sqls[min(self.calls, len(self.sqls)) - 1]

    def compose_answer(self, question, rows, answer_rules=""):
        return "테스트 답변"


# ── R-9 SQL 프롬프트 두 줄 ─────────────────────────────────────────────

def test_sql_system_has_cutoff_anchor_and_irrelevant_rule_note():
    assert "2026-08-22" in _SQL_SYSTEM
    assert "date('now')" in _SQL_SYSTEM or "date(\"now\")" in _SQL_SYSTEM
    assert "무관" in _SQL_SYSTEM
    assert "REFUSE:" in _SQL_SYSTEM


# ── R-5 거절 3단 — ② 프롬프트 층 (refusal_rules → REFUSE:) ──────────────

def test_refusal_rules_loaded_and_in_grounding(ctx):
    assert ctx.refusal_rules, "ontology/enums/_refusal.yaml 이 로드돼야 한다"
    g = build_grounding(ctx, [], ["domestic_etfs"], cross=False, question="국내 ETF 알려줘")
    assert "# 답변불가 규칙" in g and "실시간" in g


def test_extract_refuse_normalizes():
    assert extract_refuse("REFUSE: 실시간 시세는 데이터에 없다") == "REFUSE: 실시간 시세는 데이터에 없다"
    assert extract_refuse("```\nREFUSE: 전망은 없다\n```") == "REFUSE: 전망은 없다"
    assert extract_refuse("SELECT 1 LIMIT 1") == ""
    assert extract_refuse("답변 REFUSE 아님") == ""


def test_pipeline_handles_refuse_prefix(ctx):
    p = SeqPlanner(f"{REFUSE_PREFIX} 향후 수익률 전망은 데이터에 없다")
    r = answer_question("T-REF", "국내 ETF 중 내년에 수익률 오를 상품 알려줘", planner=p, ctx=ctx)
    assert "[Refuse]" in r.think_trace
    assert "확인할 수 없" in r.answer and "전망" in r.answer
    assert p.calls == 1 and r.retrieved_context == ""


# ── R-5 ① 게이트 층 — 상수 컬럼 위반 (HCX 0회) ─────────────────────────

def test_gate_rejects_constant_violation_currency(ctx):
    g = gate.check("유로(EUR)로 거래되는 해외 ETF 중 총보수가 가장 낮은 것을 알려줘", ctx, ["overseas_etfs"])
    assert g.rejected and "pd_trd_ccy" in g.reason and "USD" in g.answer


def test_gate_rejects_constant_violation_exchange(ctx):
    g = gate.check("한국거래소(KRX)에 상장된 해외 ETF를 알려줘", ctx, ["overseas_etfs"])
    assert g.rejected and "pd_mkt_id" in g.reason


def test_gate_constant_does_not_fire_on_index_name(ctx):
    # '유로스탁스50' 은 지수명이지 거래통화가 아니다 — 경계식이 없으면 정상 문항이 죽는다
    g = gate.check("유로스탁스50 지수를 추종하는 해외 ETF 알려줘", ctx, ["overseas_etfs"])
    assert not g.rejected


def test_gate_constant_only_when_routed_to_that_table(ctx):
    g = gate.check("유로로 거래되는 ETF 알려줘", ctx, ["domestic_etfs", "overseas_etfs"])
    assert not g.rejected


# ── R-4 값 검사기 ───────────────────────────────────────────────────────

def test_value_index_covers_full_alias_columns(ctx):
    assert ("domestic_etfs", "cu_fund_mgmt_co") in ctx.value_index
    assert ("domestic_bonds", "crd_grd") in ctx.value_index
    assert ("public_funds", "fd_ivst_rgn_desc") not in ctx.value_index or ctx.value_vocab.get(("public_funds", "fd_ivst_rgn_desc"))


def test_check_values_flags_unknown_literal(ctx):
    bad = "SELECT pd_nm FROM domestic_etfs WHERE cu_fund_mgmt_co = '삼성자산운용주식회사XYZ' LIMIT 5"
    v = guard.check_values(bad, ctx)
    assert len(v) == 1 and v[0].column == "cu_fund_mgmt_co"
    good = "SELECT pd_nm FROM domestic_bonds WHERE crd_grd = 'AAA' LIMIT 5"
    assert guard.check_values(good, ctx) == []
    like = "SELECT pd_nm FROM domestic_etfs WHERE cu_fund_mgmt_co LIKE '%삼성%' LIMIT 5"
    assert guard.check_values(like, ctx) == []


def test_check_values_uses_vocab_columns(ctx):
    bad = "SELECT pd_nm FROM domestic_bonds WHERE bd_inrt_tcd = '변동' LIMIT 5"
    assert guard.check_values(bad, ctx)
    good = "SELECT pd_nm FROM domestic_bonds WHERE bd_inrt_tcd = '변동금리' LIMIT 5"
    assert guard.check_values(good, ctx) == []


def test_pipeline_regenerates_once_on_value_violation(ctx):
    bad = "SELECT pd_nm FROM domestic_bonds WHERE crd_grd = 'AA-등급' LIMIT 5"
    good = "SELECT pd_nm FROM domestic_bonds WHERE crd_grd = 'AA-' LIMIT 5"
    p = SeqPlanner(bad, good)
    r = answer_question("T-VAL", "신용등급 AA- 채권 알려줘", planner=p, ctx=ctx)
    assert p.calls == 2
    assert "[Guard] 값 검사" in r.think_trace and "[Plan] 재생성" in r.think_trace
    assert "이전 SQL 의 문제" in p.groundings[1]
    # 재생성된 SQL 이 채택됐는지만 본다 — 이후 가드(신용등급 컬럼 보강 등)가 SELECT 를 넓힐 수 있어 문자열 등호는 쓰지 않는다
    assert "crd_grd = 'AA-'" in r.sql and "AA-등급" not in r.sql and r.answer == "테스트 답변"


def test_pipeline_refuses_when_regeneration_still_bad(ctx):
    bad = "SELECT pd_nm FROM domestic_bonds WHERE crd_grd = 'AA-등급' LIMIT 5"
    p = SeqPlanner(bad, bad)
    r = answer_question("T-VAL2", "신용등급 AA- 채권 알려줘", planner=p, ctx=ctx)
    assert p.calls == 2 and "확인" in r.answer and r.retrieved_context == ""


# ── R-4 0행 진단 ────────────────────────────────────────────────────────

def test_split_conjuncts_respects_parens_and_quotes():
    w = "a = 'x AND y' AND (b = 1 OR c = 2) AND d IN ('p','q')"
    assert guard.split_conjuncts(w) == ["a = 'x AND y'", "(b = 1 OR c = 2)", "d IN ('p','q')"]


def test_diagnose_zero_rows_counts_each_condition(ctx):
    sql = "SELECT pd_nm FROM domestic_bonds WHERE crd_grd = 'AAA' AND srfc_irt > 99 LIMIT 5"
    d = guard.diagnose_zero_rows(sql)
    assert d and len(d.counts) == 2
    assert d.counts[0][1] > 0 and d.counts[1][1] == 0
    assert "값 자체가 없는 조건" in d.text()


def test_pipeline_zero_rows_answer_has_diagnosis(ctx):
    sql = "SELECT pd_nm FROM domestic_bonds WHERE crd_grd = 'AAA' AND srfc_irt > 99 LIMIT 5"
    r = answer_question("T-ZERO", "표면금리 99% 넘는 AAA 채권", planner=SeqPlanner(sql), ctx=ctx)
    # 🔄 2026-08-31 밤 리드 결정 — 답변에는 자연어 사유만, 개발자 진단('조건별 단독 조회')은 trace 전용
    assert "확인되지 않습니다" in r.answer and "조건별" not in r.answer
    assert "표면금리" in r.answer and "99 초과" in r.answer          # 사유가 사용자 문장으로
    assert "[Diagnose]" in r.think_trace and "조건별" in r.think_trace


def test_user_text_dead_condition_named_in_korean(ctx):
    sql = "SELECT pd_nm FROM domestic_bonds WHERE crd_grd = 'AAA' AND srfc_irt > 99 LIMIT 5"
    d = guard.diagnose_zero_rows(sql)
    t = d.user_text()
    assert "표면금리가 99 초과인 상품" in t and "없습니다" in t
    assert "srfc_irt" not in t                                       # SQL 조각 노출 금지


def test_user_text_alive_conditions_explains_no_intersection(ctx):
    # Q10 류 — 보험회사채(99건)·6등급 각각은 있으나 교집합 0 (보험회사채는 전부 1등급)
    sql = ("SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) = '보험회사채' "
           "AND pd_risk_gcd = '16' LIMIT 5")
    d = guard.diagnose_zero_rows(sql)
    t = d.user_text()
    assert "보험회사채" in t and "6등급(매우낮은위험)" in t and "동시에 만족하는 상품은 없습니다" in t
    assert "bd_knd" not in t and "pd_risk_gcd" not in t and "'16'" not in t


def test_user_text_falls_back_to_generic_on_untranslatable(ctx):
    # OR 그룹은 한 문장으로 못 옮긴다 — 구체 열거를 포기하고 일반 문장으로 낮추되 None 은 아니다
    sql = ("SELECT pd_nm FROM domestic_bonds WHERE (crd_grd = 'AAA' OR crd_grd = 'AA+') "
           "AND srfc_irt > -1 LIMIT 5")
    d = guard.diagnose_zero_rows(sql)
    t = d.user_text()
    assert t == "조건 각각에 해당하는 상품은 있으나, 모든 조건을 동시에 만족하는 상품은 없습니다."


# ── R-1 범주값 어휘 ─────────────────────────────────────────────────────

def test_value_vocab_loaded_and_in_planner_context(ctx):
    assert "변동금리" in ctx.value_vocab[("domestic_bonds", "bd_inrt_tcd")]
    txt = ctx.planner_context(["domestic_bonds"])
    assert "bd_inrt_tcd" in txt and "변동금리" in txt


# ── R-2 규칙 2층 — triggered 규칙은 어휘가 있을 때만 ─────────────────────

def test_triggered_rule_only_with_trigger_word(ctx):
    base = ctx.planner_context(["public_funds"], question="순자산 큰 펀드 5개")
    hit = ctx.planner_context(["public_funds"], question="목표전환형 펀드 알려줘")
    assert "이름표기_구조어휘" not in base and "이름표기_구조어휘" in hit
    everything = ctx.planner_context(["public_funds"])            # question 없으면 전부 (호환)
    assert "이름표기_구조어휘" in everything


def test_always_on_rules_still_present(ctx):
    txt = ctx.planner_context(["public_funds"], question="순자산 큰 펀드 5개")
    assert "기본모수" in txt and "normalization" in txt
