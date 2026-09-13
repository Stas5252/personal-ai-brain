"""Public liveness and protected fail-closed readiness contracts."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.brain import config
from src.brain.api.app import app
from src.brain.health import check_worker_heartbeat, readiness_report


def test_liveness_endpoint_is_public():
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness_endpoint_requires_api_key():
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 401


def test_readiness_fails_closed_and_never_calls_live_model(monkeypatch):
    import src.brain.health as health

    monkeypatch.setattr(config, "GEMINI_API_KEY", "configured-not-contacted")
    monkeypatch.setattr(health, "check_database", lambda: {"ok": True})
    monkeypatch.setattr(health, "check_storage", lambda: {"ok": True})
    monkeypatch.setattr(health, "check_vector_store", lambda: (_ for _ in ()).throw(RuntimeError("spec mismatch")))
    monkeypatch.setattr(health, "check_core_knowledge", lambda: {"ok": True})
    monkeypatch.setattr(health, "check_worker_heartbeat", lambda: {"ok": True})

    payload, ready = readiness_report()
    assert ready is False
    assert payload["model_live_check"] == "not_run"
    assert payload["components"]["vector_store"]["ok"] is False


def test_worker_heartbeat_must_be_recent(monkeypatch, tmp_path):
    heartbeat = tmp_path / ".knowledge-worker-heartbeat.json"
    heartbeat.write_text(
        '{"pid": 42, "updated_at": "2025-01-01T00:00:00+00:00"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="stale"):
        check_worker_heartbeat(datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=31))
