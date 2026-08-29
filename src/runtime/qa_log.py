# -*- coding: utf-8 -*-
"""질의 로그 레코드 조립 — API 서버와 실험 CLI 가 같은 모양으로 남긴다.

🔴 로그는 실험의 산출물이다. 오답을 골라 `eval/questions_*.jsonl` 로 승격하는 입구이고,
   승격하려면 **어떤 SQL 로 그 답이 나왔는지**를 로그만 보고 알 수 있어야 한다.
   (없으면 질의를 다시 돌려야 하는데, HCX 는 같은 SQL 을 다시 만든다는 보장이 없다.)

`grounding`(근거문서 원문)은 기본으로 빼둔다 — 질의당 수 KB 라 평가 기간에는 부담이다.
실험 중에는 `LOG_GROUNDING=1` 로 켠다.
"""

from __future__ import annotations

import time
from typing import Any

from .pipeline import PipelineResult


def build_record(result: PipelineResult, elapsed_s: float, *, with_grounding: bool = False) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "question_id": result.question_id,
        "question": result.question,
        "answer": result.answer,
        "retrieved_context": result.retrieved_context,
        "think_trace": result.think_trace,
        "sql": result.sql,
        "elapsed_s": round(elapsed_s, 2),
    }
    if with_grounding:
        rec["grounding"] = result.grounding
    return rec
