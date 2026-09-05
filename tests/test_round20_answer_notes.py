# -*- coding: utf-8 -*-
"""20R — 답변 규약이 규칙 문장으로만 있어 안 지켜지던 자리 (결함 ⑧).

숫자는 맞는데 옆에 붙어야 할 한 마디가 없다. 규칙은 yaml 에 있는데 세 회차 내리 안 지켜졌으므로
**조립기가 결과 행을 보고 기계로 적는다.**

  S2 · Y4    수익률 하위 랭킹에 '누적' 주석이 없다 — 종전엔 |값| ≥ 100 일 때만 붙였다.
             그런데 −80% 대야말로 연 환산으로 읽힐 여지가 크다("3년에 −80%" → "해마다 −80%").
  FND-C01    "규모가 큰 펀드 추천해줘" 의 상위 5개가 **전부 법인용 MMF** 인데 그 말이 없다.
             clarify.사람의_선택.규모_MMF포함 이 "MMF 를 포함할지 묻거나 포함/제외 두 답을" 이라 못박은 자리.
"""
import json
import re

import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")
PROBE = "eval/probe_funds_2026-09-05_r3.json"


@pytest.fixture(scope="module")
def ctx():
    return load_context()


@pytest.fixture(scope="module")
def probe():
    with open(PROBE, encoding="utf-8") as f:
        return {r["qid"]: r for r in json.load(f)}


def _replay(ctx, rec):
    sql = re.findall(r"(?:재생성 SQL|SQL 생성)[^\n]*\n(SELECT[^\n]+)", rec["think_trace"])[-1]

    class P:
        def plan_sql(self, q, g):
            return sql

        def compose_answer(self, q, rows, answer_rules=""):
            return "HCX-CALLED"

    return answer_question(rec["qid"], rec["question"], planner=P(), ctx=ctx).answer or ""


@pytest.mark.parametrize("qid", ["S2", "Y4"])
def test_cumulative_note_on_negative_rankings(ctx, probe, qid):
    """음수 하위 랭킹에도 '누적' 을 적는다 — 극단값 경고는 붙지 않는다."""
    ans = _replay(ctx, probe[qid])
    assert "누적 수익률" in ans, ans
    assert "100%를 넘는 값은" not in ans, "극단값이 아닌데 경고가 붙었다"


def test_extreme_warning_still_conditional(ctx, probe):
    ans = _replay(ctx, probe["FND-003"])          # +387% — 극단값
    assert "누적 수익률" in ans and "100%를 넘는 값은" in ans, ans


def test_mmf_dominance_is_disclosed(ctx, probe):
    """상위가 MMF 로 채워지면 그 사실을 적는다 — 사용자는 법인 파킹 상품을 물은 게 아니다."""
    ans = _replay(ctx, probe["FND-C01"])
    assert "HCX-CALLED" not in ans
    assert "MMF" in ans and "MMF 제외" in ans, ans


def test_silent_when_the_question_named_mmf(ctx, probe):
    """FND-007 은 MMF 를 지목했다 — 이미 아는 사실이라 고지하지 않는다."""
    ans = _replay(ctx, probe["FND-007"])
    assert "상위" in ans and "중" in ans
    assert "MMF 제외" not in ans, "질문이 MMF 를 물었는데 제외를 권했다"


def test_no_note_on_non_return_axis(ctx, probe):
    """순자산 축에는 누적 주석이 붙지 않는다."""
    ans = _replay(ctx, probe["FND-001"])
    assert "누적 수익률" not in ans, ans
