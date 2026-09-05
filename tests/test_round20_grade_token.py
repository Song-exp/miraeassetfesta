# -*- coding: utf-8 -*-
"""20R — "신용등급 BBB++ 인 채권 찾아줘" (2026-09-05 서버 실측 · 사고 #76).

KG 개체 매핑이 'BBB++' 안에서 'BBB+' 를 잡아(신용등급 노드에 경계 검사가 없었다) BBB+ 100종목을 답했다 — HCX 환각이 아니라
결정층 매칭 오류. 세 자리를 고친다: ① CreditGrade 라벨도 경계 검사 조건부 + 등급꼴 라벨은 앞뒤 등급 기호도 경계 위반
② 표기에 없는 등급 토큰은 HCX 앞에서 가까운 등급을 후보로 되묻기(clarify.존재하지_않는_개체) ③ `SELECT *` 목록을 표준
컬럼 목록으로 바꿔 대표행 가드가 붙게(같은 종목이 장내·장외 행으로 두 번 나오던 자리).
과적합 점검: ①은 등급꼴 라벨 규칙이지 BBB+ 특례가 아니고, ②는 표준표·데이터 표기 선언만 읽으며(CB·CD·ABS 는 등급이 아님),
③은 `*` 에 GROUP BY 를 얹는 대신(장외행만 다른 307종목이 임의 행이 된다) 컬럼을 명시한다.
"""
import sqlite3

import pytest

from src.runtime import gate
from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import (
    _boundary_hit, _ground, answer_question, ensure_bond_select_columns, ensure_bond_representative,
    grade_token_clarify,
)

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")
Q = "신용등급 BBB++ 인 채권 찾아줘"
STAR = "SELECT *, TRIM(crd_grd) AS crd_grd FROM domestic_bonds WHERE TRIM(crd_grd) = 'BBB+' LIMIT 30"


@pytest.fixture(scope="module")
def ctx():
    return load_context()


# ── ① 경계 ──
@pytest.mark.parametrize("label, text, hit", [
    ("BBB+", "신용등급 BBB++ 인 채권", False), ("BBB+", "BBB+ 등급 채권", True), ("BBB+", "등급이 BBB+인 채권", True),
    ("AA", "AA+ 이상 채권", False), ("AA", "AA 등급", True), ("A-", "A-- 채권", False), ("A", "A+ 채권", False),
    ("BBB", "BBB0 채권", False), ("AAA", "AAA등급 국채", True),
])
def test_grade_label_boundary(label, text, hit):
    assert _boundary_hit(label, text) is hit


def test_ground_does_not_map_bbb_plus_plus(ctx):
    _, lines = _ground(Q, ctx, ["domestic_bonds"], False)
    assert not any("crd_grd='BBB+'" in ln for ln in lines)
    _, ok = _ground("신용등급 BBB+ 인 채권 찾아줘", ctx, ["domestic_bonds"], False)
    assert any("crd_grd='BBB+'" in ln for ln in ok)                # 정상 표기는 종전대로 매핑


# ── ② 되묻기 ──
def test_unknown_grade_token_is_clarified(ctx):
    ask = grade_token_clarify(Q, ["domestic_bonds"], ctx)
    assert ask and "'BBB++'" in ask and "혹시 BBB+ 를" in ask and "BBB0" in ask and "BBB-" in ask and "종목)" in ask


@pytest.mark.parametrize("q", [
    "신용등급 BBB+ 인 채권 찾아줘", "AA- 이상 회사채", "A등급 채권", "BBB 등급 채권 알려줘", "AA0 채권", "C0 등급 채권",
    "CCC 등급 채권 있어?", "씨제이 씨지브이 35CB 정보", "CD금리 연동 채권", "ABS 채권 알려줘", "한전 채권 수익률",
])
def test_valid_or_non_grade_tokens_are_not_clarified(ctx, q):
    assert grade_token_clarify(q, ["domestic_bonds"], ctx) is None


@pytest.mark.parametrize("q, best", [("AA-- 채권", "AA-"), ("A++ 등급", "A+"), ("BBB+- 채권", "BBB+")])
def test_other_malformed_grades(ctx, q, best):
    ask = grade_token_clarify(q, ["domestic_bonds"], ctx)
    assert ask and f"혹시 {best} 를" in ask


def test_clarify_is_scoped_to_bonds(ctx):
    assert grade_token_clarify(Q, ["domestic_etfs"], ctx) is None


def test_full_path_clarifies_before_hcx(ctx):
    class NoPlanner:
        def plan_sql(self, question, grounding):
            raise AssertionError("HCX 가 불리면 안 된다")

    r = answer_question("T-75", Q, planner=NoPlanner(), ctx=ctx)
    assert "[Clarify] 되묻기(결정층) — 질문의 등급 토큰" in r.think_trace and "BBB+" in r.answer


# ── ③ SELECT * 재작성 ──
def test_star_is_rewritten_and_representative_guard_then_applies(ctx):
    sql, changed = ensure_bond_select_columns(STAR, "신용등급 BBB+ 인 채권 찾아줘", ctx)
    assert changed and sql.startswith("SELECT pd_nm, pd_pbcm, bd_knd") and "*" not in sql
    assert sql.count("crd_grd") == 2                              # 표준 목록의 crd_grd 하나 + WHERE — 별칭 중복은 버린다
    grouped, g = ensure_bond_representative(sql)
    assert g and "GROUP BY pd_no" in grouped
    con = sqlite3.connect(db_path())
    try:
        names = [r[0] for r in con.execute(grouped).fetchall()]
    finally:
        con.close()
    assert len(names) == len(set(names))                          # 한진127-2 ×2 가 사라진다


def test_star_keeps_columns_the_question_names(ctx):
    sql, _ = ensure_bond_select_columns("SELECT * FROM domestic_bonds WHERE TRIM(crd_grd) = 'BBB+' LIMIT 30", "BBB+ 채권 장내종가 알려줘", ctx)
    assert "exg_close_price" in sql


@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM domestic_bonds WHERE TRIM(crd_grd) = 'BBB+'",
    "SELECT DISTINCT * FROM domestic_bonds LIMIT 5",
    "SELECT pd_nm FROM domestic_bonds LIMIT 5",
    "SELECT * FROM public_funds LIMIT 5",
    "SELECT * FROM domestic_bonds WHERE pd_no IN (SELECT pd_no FROM domestic_bonds LIMIT 1)",
])
def test_star_rewrite_leaves_other_shapes(ctx, sql):
    assert ensure_bond_select_columns(sql, "채권", ctx) == (sql, False)
