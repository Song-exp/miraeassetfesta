# -*- coding: utf-8 -*-
"""19R — 있는 것과 없는 것을 함께 묻는 질문을 통째로 거절하던 자리 (OFFICIAL-002, 주최 공식 문항).

    "국민성장펀드의 구조와 투자전략 동향 등 찾아서 알려줘"

`absent_properties` 는 속성 하나를 통째로 "없다" 고 선언하는 구조라, 질문의 절반만 부재인 경우를
표현하지 못한다. `hasInvestmentStrategy` 의 vocab 은 `구조|보수|환매…` 를 부정 전방탐색으로 빼
두었고 게이트는 설계대로 비켜 갔다 — 그런데 **HCX 플래너가 SQL 을 한 번도 안 짜고 거절**했다.

규칙: 이름이 지목한 상품이 마스터에 **실재하면** "데이터에 없다" 는 거절은 틀렸다. 수록 항목으로
조회를 세우고 부재 항목은 답변에 명시한다. 실재하지 않으면(OFFICIAL-NA-002 'Kimi') 거절이 옳다.
"""
import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import (REFUSE_PREFIX, absent_partial_note, answer_question,
                                  fund_exists, refusal_override_sql)

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

Q = "국민성장펀드의 구조와 투자전략 동향 등 찾아서 알려줘"


@pytest.fixture(scope="module")
def ctx():
    return load_context()


class _Refuser:
    """플래너가 거절만 하는 상황을 재현한다 — 실측에서 매 회차 이랬다."""

    def plan_sql(self, q, g):
        return REFUSE_PREFIX + " 제공된 데이터에는 구조와 투자전략 동향에 대한 정보가 없습니다."

    def compose_answer(self, q, rows, answer_rules=""):
        return "ROWS:\n" + rows


def test_existence_is_the_only_ground():
    assert fund_exists("국민성장") is True
    assert fund_exists("Kimi") is False
    assert fund_exists("") is False


def test_partial_absent_note_needs_a_lookahead(ctx):
    """전방탐색이 있는 선언만 '부분 부재' 대상 — 없는 선언은 게이트가 통째로 담당한다."""
    note = absent_partial_note(Q, ctx, ["public_funds"])
    assert "운용 전략" in note and "안내할 수 있습니다" in note
    assert absent_partial_note("좌수 알려줘", ctx, ["public_funds"]) == ""   # 전방탐색 없는 선언
    assert absent_partial_note(Q, ctx, ["public_funds", "domestic_etfs"]) == ""  # 테이블 미확정


def test_override_sql_returns_the_product(ctx):
    from src.runtime.pipeline import connect_readonly
    con = connect_readonly()
    try:
        rows = con.execute(refusal_override_sql("국민성장")).fetchall()
    finally:
        con.close()
    assert len(rows) == 1 and rows[0][2] == 4, "4클래스여야 한다"


def test_refusal_is_overridden_when_product_exists(ctx):
    r = answer_question("OFFICIAL-002", Q, planner=_Refuser(), ctx=ctx)
    # 2026-09-06: 개요 질의는 개요 조회 확정식이 먼저 받는다(HCX 0회) — 어느 쪽이든 "실재 상품은 거절하지 않는다" 는 같다
    assert "거절 뒤집기" in r.think_trace or "개요 조회 확정식" in r.think_trace
    ans = r.answer or ""
    assert "4" in ans and "주식혼합형" in ans, ans          # 있는 것은 답한다
    assert "운용 전략" in ans, "없는 것을 명시하지 않았다"      # 없는 것은 밝힌다


def test_refusal_stands_when_product_does_not_exist(ctx):
    r = answer_question("OFFICIAL-NA-002", "Kimi 관련 투자 상품 있어?", planner=_Refuser(), ctx=ctx)
    assert "거절 뒤집기" not in r.think_trace
    assert "확인할 수 없습니다" in (r.answer or "")
