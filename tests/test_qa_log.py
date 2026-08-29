# -*- coding: utf-8 -*-
"""질의 로그 레코드 — 실험의 산출물이 무엇을 담는가.

로그는 오답을 골라 eval 로 승격하는 입구다. **어떤 SQL 로 그 답이 나왔는지**가 없으면
회수한 로그만으로는 원인을 판정할 수 없어 같은 질의를 다시 돌려야 한다.
"""

from src.runtime.pipeline import PipelineResult
from src.runtime.qa_log import build_record


def _result():
    return PipelineResult(
        question_id="Q-001",
        question="국내 ETF 5개",
        retrieved_context="pd_nm\nKODEX 200",
        think_trace="1. [Gate] 통과",
        answer="…",
        sql="SELECT pd_nm FROM domestic_etfs LIMIT 5",
        grounding="# 스키마\ndomestic_etfs.pd_nm",
    )


def test_record_carries_sql():
    rec = build_record(_result(), elapsed_s=1.234)
    assert rec["sql"] == "SELECT pd_nm FROM domestic_etfs LIMIT 5"


def test_record_carries_five_fields_and_elapsed():
    rec = build_record(_result(), elapsed_s=1.234)
    for k in ("question_id", "question", "answer", "retrieved_context", "think_trace"):
        assert k in rec
    assert rec["elapsed_s"] == 1.23
    assert rec["ts"]


def test_grounding_included_when_asked():
    rec = build_record(_result(), elapsed_s=0.1, with_grounding=True)
    assert rec["grounding"].startswith("# 스키마")


def test_grounding_omitted_by_default():
    """평가 기간에는 근거문서까지 남기면 로그가 커진다 — 기본은 뺀다."""
    assert "grounding" not in build_record(_result(), elapsed_s=0.1)
