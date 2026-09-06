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


@needs_db
@pytest.mark.parametrize("q", ["좌수 알려줘", "설정 좌수는?", "운용역이 누구야", "기준가 추이 알려줘", "등급 이력 보여줘"])
def test_absent_property_words_are_in_domain(ctx, q):
    """🔴 2026-09-06 로컬 재생 — 없다고 **선언한** 축의 낱말은 스키마 한글명에 없다(컬럼이 없으니까).
    absent_properties 의 vocab 을 도메인 어휘에 넣지 않으면 '좌수 알려줘' 가 인사·잡담으로 오분류돼
    '미수록' 고지 대신 서비스 안내가 나간다. vocab 은 정규식이라('좌[ ]?수') 한글만 남겨 조각을 뽑는다."""
    assert not gate.is_off_domain(q, ctx), q


@needs_db
@pytest.mark.parametrize("q", ["무지개채 알려줘", "그런 상품 있어?", "아무거나 추천해줘", "몇 개야", "목록 보여줘"])
def test_lookup_ask_is_never_offdomain(ctx, q):
    """🔴 QA r1 §E(팀원 보고) — 미등록 고유명 단독 질의가 인사로 잡히면 안 된다.
    '무지개채 알려줘' 는 안내 문장이 아니라 값 부재('확인할 수 없음') 경로여야 한다(주최 §3)."""
    assert not gate.is_off_domain(q, ctx), q


@needs_db
@pytest.mark.parametrize("q", ["반가워", "잘 지내?", "수고했어", "날씨 좋네"])
def test_more_smalltalk_still_off_domain(ctx, q):
    assert gate.is_off_domain(q, ctx), q
