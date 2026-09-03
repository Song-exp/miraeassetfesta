# -*- coding: utf-8 -*-
"""enforce 슬롯 — 적용기와 로더 검증 (docs/guard_to_yaml_migration_2026-09-03.md 단계 1).

여기서 지키는 것 넷:
  ① `enforce` 는 **프롬프트로 새지 않는다** — 이 회귀가 없으면 슬롯을 붙일수록 프롬프트가 오염된다.
  ② 액션 3종이 원자적으로 동작한다 — 대상이 정확히 하나일 때만 손댄다.
  ③ **UNION 가지마다 독립 적용된다** — 코드 가드가 통째로 불개입하던 자리이고, 슬롯의 존재 이유다.
  ④ 잘못 쓴 슬롯은 **로드가 거부한다**(V1~V7 과 같은 태도).
"""
from __future__ import annotations

import copy

import pytest

from src.runtime import guard
from src.runtime.loader import load_context, validate_enforce


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def _with_slot(ctx, table, name, enforce, text="규칙 본문"):
    c = copy.deepcopy(ctx)
    c.enums[table]["query_rules"][name] = {"text": text, "enforce": enforce}
    return c


# ── ① 프롬프트 누출 금지 ──────────────────────────────────────────────────
def test_enforce_never_reaches_prompt(ctx):
    c = _with_slot(ctx, "public_funds", "_시험규칙", {
        "when": {"tables": ["public_funds"], "sql": {"lacks": ["prvo_pbff_desc"]}},
        "action": "inject_where", "sql": "sale_yn = '판매중'", "mark": "TESTMARK"})
    # `_` 접두는 원래 프롬프트에서 빠지므로 실제 이름으로 다시
    c.enums["public_funds"]["query_rules"].pop("_시험규칙")
    c = _with_slot(c, "public_funds", "시험규칙", {
        "when": {"tables": ["public_funds"]},
        "action": "inject_where", "sql": "sale_yn = '판매중'", "mark": "TESTMARK"})
    out = c.planner_context(["public_funds"], "공모펀드 몇 개야?")
    assert "- 시험규칙: 규칙 본문" in out
    for leak in ("TESTMARK", "inject_where", "enforce", "when:", "lacks"):
        assert leak not in out, f"{leak} 가 프롬프트로 샜다"


def test_shipped_slots_do_not_leak(ctx):
    """실제로 선언해 둔 슬롯(기본모수·펀드단위·기초지수)도 마찬가지."""
    for table, q in (("public_funds", "공모펀드 몇 개야?"), ("domestic_etfs", "S&P500 추종 ETF")):
        out = ctx.planner_context([table], q)
        for leak in ("BASEPOP", "FUNDUNIT", "IDXCANON", "from_pattern", "any_of_has", "mark:"):
            assert leak not in out, f"{table}: {leak} 누출"


# ── ② 액션 3종 ────────────────────────────────────────────────────────────
def test_inject_where_wraps_existing_or(ctx):
    """'WHERE a OR b' 에 그냥 AND 를 붙이면 (cond AND a) OR b 로 샌다 — 괄호로 감싸야 한다."""
    # 🔴 실제 켜진 슬롯(BASEPOP)과 **겹치지 않는 조건**을 쓴다 — 같은 조건이면 먼저 발동한 쪽에 가려
    #    이 테스트가 슬롯 순서를 재게 된다. 여기서 재려는 건 괄호 처리다.
    c = _with_slot(ctx, "public_funds", "시험모수", {
        "when": {"tables": ["public_funds"], "sql": {"lacks": ["curr_cd"]}},
        "action": "inject_where", "sql": "curr_cd = 'KRW'", "mark": "TM1"})
    sql = ("SELECT * FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
           "AND (itm_nm LIKE '%A%' OR itm_nm LIKE '%B%') ORDER BY fd_nast_suma DESC")
    out, fired = guard.apply_enforce(sql, "펀드 알려줘", ["public_funds"], set(), c)
    assert "TM1" in fired
    assert "curr_cd = 'KRW' AND (sale_yn = '판매중'" in out       # 기존 WHERE 전체를 괄호로 감쌌다
    assert "/*M:TM1*/" in out


def test_replace_expr_only_when_unambiguous(ctx):
    c = _with_slot(ctx, "public_funds", "시험카운트", {
        "when": {"tables": ["public_funds"], "sql": {"has": ["count(*)"]}},
        "action": "replace_expr", "from": "COUNT(*)",
        "sql": 'COUNT(DISTINCT {fund_key}) AS "펀드수"', "mark": "TM2"})
    one = "SELECT COUNT(*) FROM public_funds"
    out, fired = guard.apply_enforce(one, "몇 개야", ["public_funds"], set(), c)
    assert "TM2" in fired and "펀드수" in out and "or_co_xtn_itt_cd" in out

    two = "SELECT COUNT(*), COUNT(*) FROM public_funds"      # 어느 쪽인지 모른다 → 불개입
    out2, fired2 = guard.apply_enforce(two, "몇 개야", ["public_funds"], set(), c)
    assert "TM2" not in fired2 and "count(distinct" not in out2.lower()


def test_replace_predicate_capture_group(ctx):
    """확정식이 매치한 리터럴에 따라 달라지는 규칙 — {1}·{1:nospace} 로 받는다."""
    c = _with_slot(ctx, "domestic_etfs", "시험지수", {
        "when": {"tables": ["domestic_etfs"], "sql": {"has": ["cu_base_index"]}},
        "action": "replace_predicate", "from_pattern": r"cu_base_index\s*=\s*'([^']+)'",
        "sql": "ref_base_index GLOB '{1:nospace}'", "mark": "TM3"})
    sql = "SELECT * FROM domestic_etfs WHERE cu_base_index = 'S&P 500'"
    out, fired = guard.apply_enforce(sql, "S&P500 ETF", ["domestic_etfs"], set(), c)
    assert "TM3" in fired
    assert "ref_base_index GLOB 'S&P500'" in out       # 공백 제거되어 들어갔다


# ── ③ UNION 가지 독립 적용 — 슬롯의 존재 이유 ─────────────────────────────
def test_union_branches_each_get_the_rule(ctx):
    """코드 가드 ensure_fund_base_population 은 UNION 을 보면 통째로 불개입한다.
    슬롯은 가지마다 판정해 **양쪽에** 넣는다 — 교차질의 모수 누락이 여기서 닫힌다."""
    c = _with_slot(ctx, "public_funds", "시험모수2", {
        "when": {"tables": ["public_funds"], "sql": {"lacks": ["curr_cd"]}},
        "action": "inject_where", "sql": "curr_cd = 'KRW'", "mark": "TM4"})
    sql = ("SELECT '주식형' AS k, COUNT(*) FROM public_funds "
           "WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' AND zrin_btyp_nm = '주식형' "
           "UNION ALL "
           "SELECT '채권형', COUNT(*) FROM public_funds "
           "WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' AND zrin_btyp_nm = '채권형'")
    out, fired = guard.apply_enforce(sql, "유형별 몇 개야", ["public_funds"], set(), c)
    assert "TM4" in fired
    assert out.count("curr_cd = 'KRW'") == 2, "가지 하나에만 들어갔다"
    assert "UNION ALL" in out


def test_idempotent(ctx):
    """이미 표식이 있으면 두 번 발동하지 않는다."""
    c = _with_slot(ctx, "public_funds", "시험모수3", {
        "when": {"tables": ["public_funds"], "sql": {"lacks": ["prvo_pbff_desc"]}},
        "action": "inject_where", "sql": "prvo_pbff_desc = '공모'", "mark": "TM5"})
    sql = "SELECT * FROM public_funds ORDER BY fd_nast_suma DESC"
    once, _ = guard.apply_enforce(sql, "펀드", ["public_funds"], set(), c)
    twice, fired2 = guard.apply_enforce(once, "펀드", ["public_funds"], set(), c)
    assert fired2 == [] and twice == once     # 표식이 이미 있으면 어떤 슬롯도 다시 안 돈다


def test_only_enabled_slots_fire(ctx):
    """켜진 슬롯만 돈다. 2026-09-03 현재 P0-1(BASEPOP)만 enabled:true 고
    P0-2a(FUNDUNIT)·P0-3(IDXCANON)은 아직 false 다 — 항목 단위 전환의 실물 확인."""
    sql = "SELECT COUNT(*) FROM public_funds"
    _out, fired = guard.apply_enforce(sql, "공모펀드 몇 개야?", ["public_funds"], set(), ctx)
    assert "FUNDUNIT" not in fired, "아직 전환하지 않은 슬롯이 발동했다"
    assert "IDXCANON" not in fired


def test_disabled_slot_never_fires(ctx):
    """enabled:false 슬롯은 조건이 맞아도 SQL 을 건드리지 않는다."""
    c = _with_slot(ctx, "public_funds", "꺼진슬롯", {
        "enabled": False, "when": {"tables": ["public_funds"]},
        "action": "inject_where", "sql": "sale_yn = '판매중'", "mark": "OFFTEST"})
    sql = "SELECT COUNT(*) FROM public_funds WHERE prvo_pbff_desc = '공모'"
    out, fired = guard.apply_enforce(sql, "펀드", ["public_funds"], set(), c)
    assert "OFFTEST" not in fired and "OFFTEST" not in out


# ── ④ 로더 검증 ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("enf, why", [
    ({"when": {}, "action": "지원안함", "sql": "x", "mark": "M"}, "액션이 목록 밖"),
    ({"when": {}, "action": "replace_expr", "sql": "x", "mark": "M"}, "replace_expr 인데 from 없음"),
    ({"when": {}, "action": "inject_where", "sql": "x"}, "mark 없음"),
    ({"when": {"타축": 1}, "action": "inject_where", "sql": "x", "mark": "M"}, "다섯 축 밖"),
    ({"when": {"sql": {"contains": ["x"]}}, "action": "inject_where", "sql": "x", "mark": "M"}, "sql 축 밖"),
    ({"when": {"tables": ["없는테이블"]}, "action": "inject_where", "sql": "x", "mark": "M"}, "테이블 아님"),
    ({"when": {}, "action": "inject_where", "sql": "no_such_column = 1", "mark": "M"}, "실재하지 않는 컬럼"),
    ({"when": {}, "action": "inject_where", "sql": "{nosuchph}", "mark": "M"}, "모르는 자리표시자"),
])
def test_loader_rejects_bad_slot(ctx, enf, why):
    c = _with_slot(ctx, "public_funds", "나쁜슬롯", enf)
    with pytest.raises(ValueError, match="enforce 슬롯 검증 실패"):
        validate_enforce(c)


def test_loader_rejects_duplicate_mark(ctx):
    c = _with_slot(ctx, "public_funds", "중복1", {
        "when": {}, "action": "inject_where", "sql": "sale_yn = '판매중'", "mark": "DUP"})
    c = _with_slot(c, "public_funds", "중복2", {
        "when": {}, "action": "inject_where", "sql": "sale_yn = '판매중'", "mark": "DUP"})
    with pytest.raises(ValueError, match="중복"):
        validate_enforce(c)


def test_shipped_yaml_validates(ctx):
    """리포에 들어간 슬롯 선언은 검증을 통과한다 (load_context 가 이미 부르지만 명시)."""
    validate_enforce(ctx)
