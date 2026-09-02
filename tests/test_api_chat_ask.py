# -*- coding: utf-8 -*-
"""실험용 JSON 엔드포인트 `/chat/ask` — 브라우저에서 SQL·근거문서까지 본다.

평가용 `/answer` 는 5필드 고정이라 근거문서를 실을 수 없다. 검토용 필드는 여기로 나간다.
🔴 공개 URL 이므로 CHAT_TOKEN 이 맞아야 한다 — 없으면 /chat 과 같이 404 다.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from src.runtime.loader import db_path

needs_db = pytest.mark.skipif(not db_path().exists(), reason="DB 없음 — build_db.py 선행 필요")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CHAT_TOKEN", "tok")
    monkeypatch.setenv("API_LOG_DIR", str(tmp_path))
    import src.api.main as m

    importlib.reload(m)
    return TestClient(m.app)


def test_chat_ask_hides_itself_without_token(client):
    r = client.get("/chat/ask", params={"question": "국내 ETF 몇 개야?"})
    assert r.status_code == 404


def test_chat_ask_rejects_wrong_token(client):
    r = client.get("/chat/ask", params={"question": "국내 ETF 몇 개야?", "t": "nope"})
    assert r.status_code == 404


@needs_db
def test_chat_ask_returns_sql_and_grounding(client):
    r = client.get("/chat/ask", params={"question": "국내 ETF 몇 개야?", "t": "tok"})
    assert r.status_code == 200
    j = r.json()
    for k in ("question", "answer", "retrieved_context", "think_trace", "sql", "grounding"):
        assert k in j, k
    # 플래너 미연결(HCX 키 없음) 환경에서도 근거문서 조립까지는 관찰 가능해야 한다
    assert "[Gate]" in j["think_trace"]


@needs_db
def test_answer_response_stays_five_fields(client):
    """🔴 채점 스키마는 5필드 고정 — 검토용 필드가 새어 나가면 안 된다."""
    r = client.get("/answer", params={"question_id": "Q-1", "question": "국내 ETF 몇 개야?"})
    assert set(r.json()) == {"question_id", "question", "retrieved_context", "think_trace", "answer"}


def test_run_pipeline_retry_is_visible_in_trace(monkeypatch):
    """P7-c (2026-09-02 재검) — 1차 런타임 오류 후 재실행이 성공하면 trace 머리에 `0. [Retry]` 를 남긴다
    (R5 34.8s 같은 이상 지연의 원인 판별용). 1차 성공이면 붙지 않는다."""
    import src.runtime.pipeline as pl

    main = importlib.import_module("src.api.main")
    calls = {"n": 0}

    def flaky(question_id, question, planner=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("HCX 일시 오류")
        return pl.PipelineResult(question_id=question_id, question=question, think_trace="1. [Normalize] x", answer="ok")

    monkeypatch.setattr(pl, "answer_question", flaky)
    r = main.run_pipeline("Q-R", "q")
    assert calls["n"] == 2 and r.answer == "ok" and r.think_trace.startswith("0. [Retry] 1차 실행 런타임 오류 — 재실행\n1. ")
    calls["n"] = 5                                                  # 두 번째 호출부터 성공 → 1차 성공 경로
    assert not main.run_pipeline("Q-S", "q").think_trace.startswith("0. [Retry]")
