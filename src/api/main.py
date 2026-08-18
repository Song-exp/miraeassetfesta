"""평가용 REST API — 주최측 오토배치가 호출하는 엔드포인트.

규격 (PROJECT.md §7)
  GET /answer?question_id=Q-001&question=<urlencoded>
  → { question_id, question, retrieved_context, think_trace, answer }   5필드

🔴 현재는 **생존용 더미**입니다 (지시서 §4.3 ② — "내용은 하드코딩 더미여도 됩니다").
   에이전트가 완성되면 `answer_question()` 하나만 갈아끼우면 됩니다.
   응답 형태·필드명·인코딩은 지금 확정해 두고, 내용만 나중에 채웁니다.
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("api")

# 에이전트 완성 여부. 더미 응답임을 로그·헬스체크에 드러냅니다.
AGENT_READY = os.environ.get("AGENT_READY", "0") == "1"

class UTF8JSONResponse(JSONResponse):
    """🔴 규격: `Content-Type: application/json; charset=utf-8` (PROJECT.md §7 계약 조건).

    FastAPI(starlette) 기본 `JSONResponse.media_type` 은 `application/json` 이라
    charset 파라미터가 빠집니다. starlette 은 `text/*` 에만 charset 을 자동으로 붙이므로
    JSON 에는 직접 명시해야 합니다.

    본문 바이트는 원래도 UTF-8 이라 지금까지 한글이 깨지지는 않았습니다. 다만 규격이
    헤더를 명시하고 있고, 위반 시 '파싱 실패 = 무응답 처리'라 형태를 맞춥니다.
    """

    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="미래에셋 금융상품 AI Agent",
    description="평가용 REST API. 데이터 기준일 2026-07-11.",
    version="0.1.0-stub",
    default_response_class=UTF8JSONResponse,
)


class AnswerResponse(BaseModel):
    """주최측 채점기가 파싱하는 스키마. 필드명·개수를 바꾸면 안 됩니다."""

    question_id: str
    question: str
    retrieved_context: str = Field(description="DB 조회 결과 원문. 근거 제시 배점")
    think_trace: str = Field(description="각 노드의 실행 로그. 🔴 LLM 생성물이 아님")
    answer: str


def answer_question(question_id: str, question: str) -> AnswerResponse:
    """런타임 파이프라인 호출 (src/runtime/). Ground·Gate·Guard 는 가동,
    Plan(HCX SQL 생성)은 planner 연결 전까지 보류 응답.

    파이프라인 로드 실패(DB 부재 등) 시 구 스텁 문구로 강등 — 어떤 경우에도 5필드는 지킨다.
    """
    try:
        from src.runtime.pipeline import answer_question as run

        r = run(question_id, question)
        return AnswerResponse(
            question_id=r.question_id,
            question=r.question,
            retrieved_context=r.retrieved_context,
            think_trace=r.think_trace,
            answer=r.answer,
        )
    except Exception:
        log.exception("runtime pipeline unavailable — falling back to stub")
        return AnswerResponse(
            question_id=question_id,
            question=question,
            retrieved_context="",
            think_trace="1. [Error] 런타임 파이프라인 로드 실패 — 답변 보류",
            answer="현재 시스템 구축 중으로 답변을 제공할 수 없습니다.",
        )


@app.get("/health")
def health() -> dict:
    """엔드포인트 생존 확인용. 배포 모니터링에서 이걸 폴링합니다."""
    return {"status": "ok", "agent_ready": AGENT_READY, "version": app.version}


@app.get("/answer", response_model=AnswerResponse)
def answer(
    question_id: str = Query(..., description="문항 ID"),
    question: str = Query(..., description="질의 원문"),
) -> AnswerResponse:
    t0 = time.perf_counter()
    result = answer_question(question_id, question)
    dt = time.perf_counter() - t0
    log.info("answer qid=%s dt=%.3fs q=%r", question_id, dt, question[:80])
    return result


def _fallback(request: Request, trace: str) -> JSONResponse:
    """🔴 어떤 경우에도 200 + 5필드 JSON 을 반환합니다.

    채점기 입장에서 422/500 은 '파싱 실패'이고, 그건 '답변 불가'보다 나쁩니다.
    형태를 지키면 최소한 오답으로 채점되지, 무응답으로 처리되지는 않습니다.
    """
    return UTF8JSONResponse(
        status_code=200,
        content=AnswerResponse(
            question_id=request.query_params.get("question_id", ""),
            question=request.query_params.get("question", ""),
            retrieved_context="",
            think_trace=trace,
            answer="확인할 수 없습니다.",
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def invalid_params(request: Request, exc: RequestValidationError) -> JSONResponse:
    """필수 파라미터 누락·형식 오류. FastAPI 기본 422 스키마는 5필드가 아닙니다."""
    log.warning("invalid params: %s", exc.errors())
    return _fallback(request, "1. [Error] 요청 파라미터 오류 — 답변 불가로 처리")


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error")
    return _fallback(request, "1. [Error] 내부 처리 오류 — 답변 불가로 처리")
