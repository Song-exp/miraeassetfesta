# -*- coding: utf-8 -*-
"""20R — 어려운 난이도 2문항 재점검 2차 (2026-09-05 · 사고 #72·#73·#74).

#72 "한전 채권 금리가 요즘 어떻게 움직였어?" — 스냅샷 데이터에 이력 축이 없는데 HCX 가 만기순 30행을 시간순인 양 읽어
    "하락 추세" 를 서술했다. → yaml absent_properties.hasYieldHistory (게이트 어휘 · HCX 0회). 코드 변경 없음.
#73 "포스코퓨처엠 채권이랑 신용등급·잔존만기가 비슷한 다른 회사채 추천해줘" — `포스코퓨처엠 OR 회사채` 로 회사채 전체 목록.
    → similar_bond_clarify(기준이 여러 구간이면 되묻기) · ensure_similar_bond_query(확정식, 축·폭은 yaml similarity_axes).
#74 답변에 `TRIM(std_pd_mcls_nm)` 라벨이 새어 나감 → _bare_header.
과적합 점검: 이력 어휘는 동사에 걸고 시점 부사·조건형에는 안 걸린다 · 유사도 축은 yaml 표에서만 온다 · 폭은 상대폭.
"""
import re
import sqlite3

import pytest

from src.runtime import gate
from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import (
    _bare_header, _bond_list_answer, answer_question, ensure_similar_bond_query, similar_bond_clarify,
    strip_unasked_maturity_cap,
)

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

Q3 = "한전 채권 금리가 요즘 어떻게 움직였어?"
Q4 = "포스코퓨처엠 채권이랑 신용등급·잔존만기가 비슷한 다른 회사채 추천해줘"
Q4N = "포스코퓨처엠23-1 이랑 신용등급·잔존만기가 비슷한 다른 회사채 추천해줘"
GARBAGE = "SELECT pd_nm FROM domestic_bonds WHERE TRIM(pd_pbcm)='(주)포스코퓨처엠' OR TRIM(std_pd_mcls_nm)='회사채' LIMIT 5"


@pytest.fixture(scope="module")
def ctx():
    return load_context()


# ── #72 이력 축 부재 — 선언만으로 게이트가 끊는다 ────────────────────────────────────
@pytest.mark.parametrize("q", [
    Q3, "삼성전자 채권 수익률이 최근에 올랐어?", "국고채 금리 추이 알려줘", "회사채 가격이 떨어진 종목",
    "한전채 금리 흐름 어때", "수익률이 오른 채권 정리해줘", "채권 금리 동향", "가격 변동이 큰 채권", "금리가 얼마나 내렸어",
])
def test_yield_history_is_rejected_by_declaration(ctx, q):
    g = gate.check(q, ctx, ["domestic_bonds"])
    assert g.rejected and "hasYieldHistory" in g.reason
    assert "발행일별 표면금리" in g.answer                      # 대체 안내(substitute.note)


@pytest.mark.parametrize("q", [
    "금리가 오르면 어떤 채권이 유리해?", "최근 발행된 채권 표면금리 높은 순", "변동금리 채권 알려줘", "수익률 변동성이 낮은 채권",
    "요즘 금리 높은 채권 추천", "금리 인상기에 좋은 채권", "수익률 높은 순 5개", "금리가 떨어지면 채권 가격은 어떻게 돼?",
    "한전 채권 금리 얼마야", "수익률 4% 넘는 채권", "가격이 액면보다 낮은 채권", "신용등급 대비 수익률이 오른 채권",
])
def test_yield_history_vocab_does_not_hit_concept_or_snapshot_questions(ctx, q):
    g = gate.check(q, ctx, ["domestic_bonds"])
    assert not (g.rejected and "hasYieldHistory" in (g.reason or ""))


def test_history_declaration_is_scoped_to_bonds(ctx):
    # ETF 는 기간수익률 컬럼이 있다 — 채권 선언이 다른 도메인에 번지지 않는다
    g = gate.check("채권형 국내 ETF 중 최근 1년 수익률이 가장 높은 5개를 알려줘.", ctx, ["domestic_etfs"])
    assert "hasYieldHistory" not in (g.reason or "")


# ── #73 유사채권 — 되묻기 · 확정식 ──────────────────────────────────────────────────
def test_multi_bucket_anchor_asks_which_maturity(ctx):
    ask = similar_bond_clarify(Q4, ["domestic_bonds"], ctx)
    assert ask and "AA-" in ask and "단기" in ask and "중기" in ask and "장기" in ask and "어느 만기대" in ask


def test_named_anchor_does_not_ask(ctx):
    assert similar_bond_clarify(Q4N, ["domestic_bonds"], ctx) is None


def test_similarity_query_is_built_from_yaml_axes(ctx):
    sql, note = ensure_similar_bond_query(GARBAGE, Q4N, ctx)
    assert note and "포스코퓨처엠23-1" in note and "AA-" in note and "±25%" in note
    assert "TRIM(crd_grd) IN ('AA-')" in sql
    assert "remaining_days BETWEEN 658.5 AND 1097.5" in sql       # 878 ±25% (하한 90일보다 크다)
    assert "TRIM(pd_pbcm) <> '(주)포스코퓨처엠'" in sql              # '다른' → 기준 발행사 제외
    assert "TRIM(bd_knd) IN ('일반회사채')" in sql                    # same_kind
    assert "bd_ofr_tcd <> '사모'" in sql and "pd_risk_gcd <> '11'" in sql
    assert not re.search(r"OR", sql)
    con = sqlite3.connect(db_path())
    try:
        rows = con.execute(sql).fetchall()
    finally:
        con.close()
    assert len(rows) == 5 and all(r[2] == "AA-" for r in rows) and all("포스코" not in r[0] for r in rows)
    assert all(658.5 <= r[5] <= 1097.5 for r in rows)


def test_similarity_query_keeps_issuer_without_exclusion_word(ctx):
    sql, note = ensure_similar_bond_query(GARBAGE, "포스코퓨처엠23-1 이랑 잔존만기가 비슷한 회사채 골라줘", ctx)
    assert note and "TRIM(pd_pbcm) <>" not in sql
    assert "TRIM(crd_grd) IN" not in sql and "remaining_days BETWEEN" in sql   # 축을 말했으면 그 축만


def test_similarity_query_leaves_non_similar_questions(ctx):
    for q in ("포스코퓨처엠 채권 수익률 알려줘", "AA- 등급 회사채 추천해줘"):
        assert ensure_similar_bond_query(GARBAGE, q, ctx) == (GARBAGE, None)
        assert similar_bond_clarify(q, ["domestic_bonds"], ctx) is None


def test_single_bond_issuer_answers_directly(ctx):
    con = sqlite3.connect(db_path())
    try:
        issuer = con.execute(
            "SELECT TRIM(pd_pbcm) FROM domestic_bonds WHERE mat_dt >= 20260824 AND curr_cd='KRW' AND crd_grd IS NOT NULL "
            "AND TRIM(std_pd_mcls_nm)='회사채' AND TRIM(pd_pbcm) LIKE '%한온시스템%' GROUP BY 1 HAVING COUNT(DISTINCT pd_no) >= 1 LIMIT 1"
        ).fetchone()[0]
    finally:
        con.close()
    q = f"{issuer.replace('(주)', '')} 채권이랑 비슷한 다른 회사채 추천해줘"
    # 한온시스템은 종목이 여럿이라 구간이 갈리면 되묻고, 한 구간이면 확정식 — 둘 중 하나는 반드시 발동한다
    ask = similar_bond_clarify(q, ["domestic_bonds"], ctx)
    sql, note = ensure_similar_bond_query(GARBAGE, q, ctx)
    assert ask or note


def test_cap_guard_leaves_similarity_window(ctx):
    sql, _ = ensure_similar_bond_query(GARBAGE, Q4N, ctx)
    assert strip_unasked_maturity_cap(sql, Q4N) == (sql, False)


class GarbagePlanner:
    def plan_sql(self, question, grounding):
        return GARBAGE

    def compose_answer(self, question, rows, answer_rules=""):
        return "HCX 산문"


def test_full_path_named_anchor(ctx):
    r = answer_question("T-73", Q4N, planner=GarbagePlanner(), ctx=ctx)
    assert "[Guard] 유사채권 확정식" in r.think_trace
    assert "기준 포스코퓨처엠23-1" in r.answer and "수익률 높은 순 상위 5개" in r.answer
    assert r.answer.count("\n") >= 5 and "HCX 산문" not in r.answer
    assert "위험등급이 매우 높은(1등급) 채권과 사모 채권은 제외했습니다" in r.answer


def test_full_path_multi_anchor_clarifies(ctx):
    r = answer_question("T-73b", Q4, planner=GarbagePlanner(), ctx=ctx)
    assert "[Clarify] 되묻기(결정층) — 유사채권" in r.think_trace and r.sql in (None, "")
    assert "어느 만기대" in r.answer


# ── #74 TRIM 헤더 복원 ───────────────────────────────────────────────────────────────
def test_bare_header():
    assert _bare_header("TRIM(std_pd_mcls_nm)") == "std_pd_mcls_nm"
    assert _bare_header("domestic_bonds.pd_nm") == "pd_nm"
    assert _bare_header("MAX(applied_yield)") == "MAX(applied_yield)"


def test_list_answer_labels_trimmed_headers():
    sql = "SELECT pd_nm, TRIM(std_pd_mcls_nm), TRIM(pd_pbcm), applied_yield FROM domestic_bonds WHERE applied_yield > 0 ORDER BY applied_yield DESC LIMIT 1"
    rows = "pd_nm | TRIM(std_pd_mcls_nm) | TRIM(pd_pbcm) | applied_yield\n테스트1 | 회사채 | 테스트(주) | 4.5"
    out = _bond_list_answer(sql, rows, 1, "수익률 높은 회사채")
    assert out and "TRIM(" not in out and "대분류 회사채" in out and "발행사 테스트(주)" in out
