# -*- coding: utf-8 -*-
"""paired v2(2026-08-31) 실측 실패에서 나온 가드 2건 — 곱슬따옴표 정규화 · 컬럼 환각 검출."""
import glob
import json
import os

import pytest

from src.runtime import guard
from src.runtime.loader import db_path, load_context

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def test_unknown_columns_catches_hallucination(ctx):
    # paired v2 실측 — 교차 혼동 환각: domestic_etfs 에 채권 컬럼(pd_risk_gcd)·없는 컬럼(cu_last_aum)
    bad = "SELECT pd_nm, cu_last_aum FROM domestic_etfs WHERE pd_risk_gcd = '11' LIMIT 5"
    unk = guard.unknown_columns(bad, ctx)
    assert "cu_last_aum" in unk and "pd_risk_gcd" in unk


def test_unknown_columns_ok_for_real_derived_columns(ctx):
    # remaining_days·after_tax_yield 는 채권 담당의 실존 파생 컬럼 — 오탐이면 안 된다
    ok = "SELECT pd_nm, remaining_days FROM domestic_bonds WHERE after_tax_yield > 3 LIMIT 5"
    assert guard.unknown_columns(ok, ctx) == []


def test_unknown_columns_no_false_positive_on_gold(ctx):
    """전 gold SQL 에서 오탐 0 이어야 한다 — AS 별칭·내장함수·문자열 리터럴이 걸리면 안 된다."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for f in sorted(glob.glob(os.path.join(root, "eval", "questions_*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            if not line.strip():
                continue
            q = json.loads(line)
            if q.get("gold_sql"):
                unk = guard.unknown_columns(q["gold_sql"], ctx)
                assert not unk, f"{q['qid']}: 오탐 {unk}"


def test_curly_quotes_normalized(ctx):
    from src.runtime.pipeline import answer_question

    class P:
        def plan_sql(self, q, g):
            return "SELECT pd_no FROM domestic_bonds WHERE TRIM(bd_knd) = ‘국고채권’ LIMIT 5"

        def compose_answer(self, q, rows, answer_rules=""):
            return "t"

    r = answer_question("T-QT", "국고채권 알려줘", planner=P(), ctx=ctx)
    assert "따옴표 정규화" in r.think_trace
    assert "‘" not in (r.sql or "")
