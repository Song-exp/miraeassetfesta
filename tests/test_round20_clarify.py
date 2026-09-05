# -*- coding: utf-8 -*-
"""20R — 대상이 특정되지 않은 속성값 질의를 되묻는다 (FND-C02, 1·2·3차 내리 ❌).

    "삼성 펀드 보수 알려줘"   → '삼성' 이름 펀드는 204개다

1차는 질문이 '보수' 인데 **순자산 목록 30개**를 냈고, 2·3차는 보수는 냈으나 **클래스 단위
목록을 쏟았다**. 어느 쪽도 사용자가 물은 답이 아니다.

`clarify.펀드이름` 이 *"브랜드·운용사 이름만으로 '~펀드' 를 물으면 … CLARIFY 로 되묻는다"* 라고
문안까지 적어 뒀는데 세 회차 모두 무시됐다. 결정층에서 못 박는다.

🔴 목록이 정답인 질의와 갈라야 한다 — T13("미국에 투자하는 공모펀드 알려줘")은 **어떤 펀드인지**
   를 묻는다. 속성 낱말이 없으므로 되묻지 않는다.
"""
import json
import re

import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question, clarify_underspecified_lookup

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


@pytest.fixture(scope="module")
def probe():
    with open("eval/probe_funds_2026-09-05_r3.json", encoding="utf-8") as f:
        return {r["qid"]: r for r in json.load(f)}


@pytest.mark.parametrize("q, token, funds, expect, why", [
    ("삼성 펀드 보수 알려줘", None, 204, True, "속성 낱말 + 상품 미특정 + 후보 다수"),
    ("미국에 투자하는 공모펀드 알려줘", None, 98, False, "🔴 어떤 펀드인지 묻는 질의 — 목록이 정답이다"),
    ("이름이 삼성으로 시작하는 공모펀드는 몇 개야?", None, 217, False, "개수 질의"),
    ("삼성 펀드 중 순자산 가장 큰 3개", None, 204, False, "랭킹 질의"),
    ("미래에셋코어테크 펀드 보수 알려줘", "미래에셋코어테크", 2, False, "상품이 특정됐다"),
    ("흥국 펀드 보수 알려줘", None, 3, False, "후보가 적으면 그냥 답한다"),
])
def test_trigger_conditions(q, token, funds, expect, why):
    assert bool(clarify_underspecified_lookup(q, token, funds)) is expect, why


def _replay(ctx, rec):
    sql = re.findall(r"(?:재생성 SQL|SQL 생성)[^\n]*\n(SELECT[^\n]+)", rec["think_trace"])[-1]

    class P:
        def plan_sql(self, q, g):
            return sql

        def compose_answer(self, q, rows, answer_rules=""):
            return "HCX-LIST"

    return answer_question(rec["qid"], rec["question"], planner=P(), ctx=ctx)


def test_fnd_c02_asks_back(ctx, probe):
    r = _replay(ctx, probe["FND-C02"])
    assert "[Clarify]" in r.think_trace
    ans = r.answer or ""
    assert "204" in ans and "특정 펀드명" in ans, ans
    assert "HCX-LIST" not in ans, "목록을 쏟았다"


@pytest.mark.parametrize("qid", ["T13", "FND-C01"])
def test_list_and_ranking_are_untouched(ctx, probe, qid):
    """목록·랭킹 질의는 되묻지 않는다 — 되묻으면 답할 수 있는 질문을 거절하는 셈이다."""
    r = _replay(ctx, probe[qid])
    assert "[Clarify]" not in r.think_trace
