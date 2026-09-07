"""
Test Suite: Open WebUI Federation via OpenAI-Compatible /v1 Endpoints.
Verifies:
1. /v1/models advertises personal-ai-brain model.
2. /v1/chat/completions returns standard non-streaming payload with usage & role assistant.
3. /v1/chat/completions with stream=True returns standard SSE stream terminating with [DONE].
4. Unauthenticated requests to /v1 endpoints return HTTP 401.
"""
import json
import pytest
from fastapi.testclient import TestClient

from src.brain.api.app import app

@pytest.fixture
def auth_client():
    import os
    key = os.environ.get('BRAIN_API_KEY', 'regression-only-not-a-production-key-0001')
    return TestClient(app, headers={"Authorization": f"Bearer {key}"})

@pytest.fixture
def unauth_client():
    return TestClient(app)


def test_v1_models_endpoint(auth_client):
    """Verifies that Open WebUI can discover the personal-ai-brain model."""
    res = auth_client.get("/v1/models")
    assert res.status_code == 200
    data = res.json()
    assert data["object"] == "list"
    assert len(data["data"]) >= 1

    model_ids = [m["id"] for m in data["data"]]
    assert "personal-ai-brain" in model_ids


def test_v1_chat_completions_non_streaming(auth_client):
    """Verifies standard non-streaming OpenAI chat completion format."""
    payload = {
        "model": "personal-ai-brain",
        "messages": [
            {"role": "user", "content": "Привет! Какие услуги предлагает фотограф?"}
        ],
        "stream": False
    }
    res = auth_client.post("/v1/chat/completions", json=payload)
    assert res.status_code == 200
    data = res.json()

    # OpenAI schema conformance
    assert "id" in data
    assert data["object"] == "chat.completion"
    assert "created" in data
    assert data["model"] == "personal-ai-brain"
    assert len(data["choices"]) == 1

    choice = data["choices"][0]
    assert choice["message"]["role"] == "assistant"
    assert len(choice["message"]["content"]) > 0
    assert choice["finish_reason"] == "stop"

    # Usage statistics
    assert "usage" in data
    assert data["usage"]["total_tokens"] > 0


def test_v1_chat_completions_sse_streaming(auth_client):
    """Verifies SSE streaming with chunk deltas ending with [DONE]."""
    payload = {
        "model": "personal-ai-brain",
        "messages": [
            {"role": "user", "content": "Расскажи кратко о подготовке к портретной съемке."}
        ],
        "stream": True
    }
    res = auth_client.post("/v1/chat/completions", json=payload)
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]

    # Read SSE events from body
    lines = res.text.split("\n")
    data_lines = [l for l in lines if l.startswith("data: ")]

    assert len(data_lines) >= 2, "Stream must deliver at least one content chunk and a [DONE] chunk"
    assert data_lines[-1] == "data: [DONE]"

    # Validate first chunk format
    first_payload = json.loads(data_lines[0].replace("data: ", ""))
    assert first_payload["object"] == "chat.completion.chunk"
    assert first_payload["model"] == "personal-ai-brain"
    assert len(first_payload["choices"]) == 1
    assert "delta" in first_payload["choices"][0]


def test_v1_unauthorized_access(unauth_client):
    """Verifies that missing auth credentials reject with 401."""
    res_models = unauth_client.get("/v1/models")
    assert res_models.status_code == 401

    res_chat = unauth_client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "test"}]})
    assert res_chat.status_code == 401
