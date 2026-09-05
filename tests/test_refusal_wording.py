"""거절 답변의 고객 어투 — 결론→이유→대안, 개발자 표기 금지 (2026-09-05 wording).

배경: "2026년 9월 발행 회사채" · "애플 달러 채권" 실측 답변이 과정 설명(컬럼명·행수·원본 레코드명)으로 읽혔다.
🔴 형식만 바꾸고 판정은 안 바뀐다 — 오거절 교정 가드가 거절문을 알아보는 정규식(_REFUSAL_ANSWER)이 새 문장도 잡아야 하고,
   기존 앵커 문구('존재하지 않는'·'AAA~D'·'체계에 있으나'·'수록 범위')는 그대로 남아야 한다.
"""
import re

import pytest

from src.runtime import wording
from src.runtime.loader import load_context
from src.runtime.pipeline import _REFUSAL_ANSWER, answer_question

_IDENT = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b")   # snake_case 컬럼명


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def test_customer_text_strips_only_identifier_parentheticals():
    assert wording.customer_text("현재 등급(crd_grd)과 부여일(crd_grd_dt)만 있습니다") == "현재 등급과 부여일만 있습니다"
    assert wording.customer_text("규모는 순자산(fd_nast_suma), 가격은 기준가(bns_bpr, 기준일 단일 스냅샷)로") == "규모는 순자산, 가격은 기준가로"
    # 고객 정보 괄호는 남긴다
    keep = "원화(KRW) 표시 채권만 (기준일 2026-08-24) 위험등급(1~6등급)"
    assert wording.customer_text(keep) == keep


def test_refusal_joins_three_sentences_and_regex_still_detects():
    a = wording.refusal("X는 확인할 수 없습니다", "이유", "다시 질문해 주세요")
    assert a == "X는 확인할 수 없습니다. 이유. 다시 질문해 주세요."
    assert _REFUSAL_ANSWER.search(a)
    assert _REFUSAL_ANSWER.search(wording.after_cutoff("2026-08-24"))


def test_after_cutoff_answer_is_customer_facing(ctx):
    r = answer_question("W-01", "2026년 9월에 새로 발행된 회사채 목록 정리해줘", ctx=ctx)
    a = r.answer
    assert "2026-08-24" in a and "확인할 수 없습니다" in a and "다시 질문" in a
    assert "이후 시점의 정보는" not in a and not _IDENT.search(a)


def test_currency_gate_answer_has_no_record_names(ctx):
    r = answer_question("W-02", "애플이 발행한 달러 채권 금리 알려줘", ctx=ctx)
    a = r.answer
    assert "[Gate] 기각" in r.think_trace
    assert a.startswith("달러 등 외화 표시 채권은 확인할 수 없습니다")
    assert "BAC" not in a and "1행" not in a and "수록 범위" in a and "다시" not in a[:20]


def test_absent_history_answer_has_no_column_names(ctx):
    r = answer_question("W-03", "최근 6개월 사이에 신용등급이 떨어진 채권 정리해줘", ctx=ctx)
    a = r.answer
    assert "[Gate] 기각" in r.think_trace and "hasCreditGradeHistory" in r.think_trace
    assert a.startswith("신용등급이 오르거나 내린 이력은 확인할 수 없습니다") and not _IDENT.search(a)
    r2 = answer_question("W-04", "한전 채권 금리가 요즘 어떻게 움직였어?", ctx=ctx)
    assert "hasYieldHistory" in r2.think_trace and not _IDENT.search(r2.answer) and "다시 물어봐" in r2.answer


def test_grade_answers_keep_anchor_phrases_and_add_alternative(ctx):
    a = answer_question("W-05", "신용등급 AAAA인 채권 찾아줘", ctx=ctx).answer
    assert "존재하지 않는" in a and "AAA~D" in a and a.endswith("다시 질문해 주시면 조회해 드리겠습니다.")
    assert "체계입니다" not in a
    b = answer_question("W-06", "신용등급 CCC인 채권 알려줘", ctx=ctx).answer
    assert "체계에 있으나" in b and "해당 등급의 채권이 없습니다" in b and "다시 질문" in b


def test_clarify_path_is_not_refusal_shaped(ctx):
    """되묻기는 이 형식을 타지 않는다 — 역질문은 유효 답변이라 '확인할 수 없습니다' 로 시작하면 거절로 채점된다."""
    r = answer_question("W-07", "가장 위험한 채권이 뭐야?", ctx=ctx)
    assert "[Clarify]" in r.think_trace and not r.answer.startswith("요청하신") and "확인할 수 없습니다" not in r.answer
