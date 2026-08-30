# -*- coding: utf-8 -*-
"""공모펀드 query_rules 가 플래너에 실리는 형태 — 2026-08-30 결정: 이름 파생 컬럼(nm_*) 대신 규칙.

- 규칙은 존재하는 컬럼만 가리켜야 한다. nm_* 는 DB 에 없다 — 프롬프트에 실리면 플래너가 없는 컬럼으로 SQL 을 쓴다.
- 랭킹·Top-N 은 클래스(행)가 아니라 펀드 단위(or_co + mtco_itm_no) — 한화2.2배레버리지 6클래스가 TOP5 를 도배하는 함정.
"""

import re
import sqlite3

import pytest

from src.runtime.loader import db_path, load_context

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음 — build_db.py 선행 필요")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def test_fund_rules_reference_only_existing_columns(ctx):
    rules = ctx.planner_context(["public_funds"])
    cols = {c for c, _, _ in ctx.schema["public_funds"]}
    referenced = set(re.findall(r"\bnm_[a-z_]+", rules))
    assert not referenced - cols, f"DB 에 없는 컬럼을 규칙이 가리킨다: {sorted(referenced - cols)}"
    assert "name_features" not in rules


def test_fund_topn_rule_groups_by_fund_not_class(ctx):
    rules = ctx.planner_context(["public_funds"])
    assert "대표행" in rules
    m = re.search(r"대표행:.*?(?=\n- |\Z)", rules, re.S)
    assert m and "mtco_itm_no" in m.group(0) and "or_co_xtn_itt_cd" in m.group(0)


# ── 2026-08-30 저녁 — 수치 축: 컬럼 정책이 답변 단계에 실리는가 ──────────────

def test_fund_answer_rules_reach_compose_stage(ctx):
    """columns.*.answer_policy 에만 있던 규약(누적 수익률·위험등급 방향·보수 ‰)은 compose_answer 에 안 갔다 — answer_rules 로 옮긴다."""
    a = ctx.answer_context(["public_funds"])
    assert "누적" in a
    assert "작을수록" in a          # 제로인 위험등급 1~6 방향
    assert "‰" in a and "10" in a   # 보수 단위 환산
    assert "클래스" in a            # 대표행 병기


def test_fund_extreme_return_rule_warns_not_excludes(ctx):
    """1년수익률 >100% 가 889건 — 채권 8/29 결정(빼지 않고 알린다)을 펀드에도. 규칙명 수익률극단값."""
    r = ctx.planner_context(["public_funds"])
    m = re.search(r"- 수익률극단값:.*?(?=\n- |\Z)", r, re.S)
    assert m, "수익률극단값 규칙 없음"
    assert "제외" not in m.group(0).split("주의")[0] or "제외하지" in m.group(0)


def test_fund_clarify_rules_exist(ctx):
    c = ctx.clarify_context(["public_funds"])
    assert "수익률" in c and "보수" in c


# ── D-4-04 — absent(CreditGrade, public_funds) 선언이 게이트에서 실제로 기각하는가 ──

def test_fund_credit_grade_query_rejected_by_absent(ctx):
    """펀드에는 신용등급 컬럼이 없다(shared/credit_grade.yaml absent_in). 2026-08-30 실측: _ENTITY_HINTS 에
    '신용등급' 항목이 없어 선언이 한 번도 발동하지 않았다 — 답변불가 문항이 통과해 HCX 가 지어낼 위험."""
    from src.runtime.pipeline import answer_question
    r = answer_question("T-CG", "신용등급 AAA인 공모펀드 알려줘", ctx=ctx)
    assert "[Gate] 기각" in r.think_trace and "CreditGrade" in r.think_trace
    assert "제공되지" in r.answer or "확인할 수 없" in r.answer


def test_bond_credit_grade_query_still_passes_absent(ctx):
    """채권은 신용등급이 있다 — 힌트 추가가 채권 질의를 기각하면 안 된다 (enum 검사로만 간다)."""
    from src.runtime.pipeline import answer_question
    r = answer_question("T-CG2", "신용등급 AAA인 채권 알려줘", ctx=ctx)
    assert "속성이 정의되어 있지 않음" not in r.think_trace
