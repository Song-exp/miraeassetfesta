# -*- coding: utf-8 -*-
"""Base URL 을 사람이 브라우저로 열었을 때 (2026-09-06) — 안내 페이지 · 질문 없는 /answer 는 사용법을 answer 에 적는다.

계약은 그대로다: /answer 는 어떤 경우에도 200 + 5필드 JSON.
"""
import importlib

import pytest
from fastapi.testclient import TestClient

FIELDS = {"question_id", "question", "retrieved_context", "think_trace", "answer"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("API_LOG_DIR", str(tmp_path))
    import src.api.main as m

    importlib.reload(m)
    return TestClient(m.app)


def test_root_is_a_usage_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "/answer?question_id=" in r.text and "/health" in r.text


def test_answer_without_question_keeps_contract_and_explains(client):
    r = client.get("/answer")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == FIELDS
    assert "question_id=<문항ID>&question=<질문>" in body["answer"]
    assert "/answer?question_id=Q1&question=" in body["answer"]


def test_answer_with_question_but_missing_id_is_plain_fallback(client):
    r = client.get("/answer", params={"question": "국고채 몇 종목"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == FIELDS and body["answer"] == "확인할 수 없습니다."
    assert "요청 파라미터 오류" in body["think_trace"]
