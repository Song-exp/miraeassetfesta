# -*- coding: utf-8 -*-
"""도메인 밖(인사·잡담) 게이트 — 2026-09-06 '안녕' 실측.

어휘는 손 목록이 아니라 스키마 한글명·yaml korean_name·synonyms·상품 명사에서 만든 두 글자 조각이다.
잘못 기각이 잘못 통과보다 나쁘므로 숫자·영문이 있거나 조각이 하나라도 걸리면 도메인 안으로 본다.
"""
import pytest

from src.runtime import gate
from src.runtime import pipeline as P
from src.runtime.loader import db_path

needs_db = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return P.load_context()


@needs_db
@pytest.mark.parametrize("q", ["안녕", "안녕하세요", "고마워요", "뭐해?", "너 누구야", "ㅋㅋㅋ"])
def test_smalltalk_is_off_domain(ctx, q):
    assert gate.is_off_domain(q, ctx), q


@needs_db
@pytest.mark.parametrize("q", [
    "국고채는 총 몇 종목이야?", "수익률 제일 높은 거 5개만 알려줘", "삼성전자 담은 ETF", "VOO 뭐야",
    "만기 긴 걸 사면 뭐가 위험해", "보수 낮은 순으로", "기준가 알려줘", "1년 안에 만기", "위험한 거 말고 안전한 거",
])
def test_finance_questions_stay_in_domain(ctx, q):
    assert not gate.is_off_domain(q, ctx), q


class _P:
    def __init__(self):
        self.calls = 0

    def plan_sql(self, q, g):
        self.calls += 1
        return "SELECT 1"

    def compose_answer(self, q, rows, answer_rules=""):
        return "HCX"


@needs_db
def test_pipeline_answers_greeting_without_planning(ctx):
    p = _P()
    r = P.answer_question("T", "안녕", planner=p, ctx=ctx)
    assert p.calls == 0
    assert "[Gate] 도메인 밖" in r.think_trace
    assert r.answer == gate.OFF_DOMAIN_ANSWER and "국고채" in r.answer


@needs_db
def test_pipeline_still_plans_for_vague_but_financial_question(ctx):
    p = _P()
    P.answer_question("T", "수익률 제일 높은 거 5개만 알려줘", planner=p, ctx=ctx)
    assert p.calls >= 1
