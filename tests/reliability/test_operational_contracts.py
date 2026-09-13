"""Regression tests for least privilege, metrics, and maintenance safety."""
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from scripts.reindex_vectors import apply, rollback
from src.brain.api.app import app

ROOT = Path(__file__).resolve().parents[2]


def test_compose_corpus_and_secrets_are_service_scoped():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    corpus_services = set()
    for name, service in services.items():
        for volume in service.get("volumes", []):
            if isinstance(volume, dict) and volume.get("target") == "/app/corpus":
                corpus_services.add(name)
    assert corpus_services == {"knowledge_bootstrap", "knowledge_worker"}
    assert "GEMINI_API_KEY" not in services["db_migrate"]["environment"]
    assert "BRAIN_API_KEY" not in services["db_migrate"]["environment"]
    assert "BRAIN_API_KEY" not in services["knowledge_worker"]["environment"]
    assert "brain_api" not in services["knowledge_worker"].get("depends_on", {})


def test_metrics_are_protected_and_do_not_probe_live_model(monkeypatch):
    import src.brain.health as health

    monkeypatch.setattr(health, "readiness_report", lambda: ({
        "status": "degraded",
        "components": {
            "database": {"ok": True}, "storage": {"ok": True},
            "vector_store": {"ok": False}, "core_knowledge": {"ok": True},
            "worker": {"ok": True},
        },
    }, False))
    client = TestClient(app)
    assert client.get("/metrics").status_code == 401
    response = client.get("/metrics", headers={"Authorization": "Bearer regression-only-not-a-production-key-0001"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "brain_ready 0" in response.text
    assert 'brain_component_up{component="vector_store"} 0' in response.text


def test_vector_maintenance_requires_exact_confirmation():
    try:
        apply("wrong", 10)
    except RuntimeError as exc:
        assert "--confirm REINDEX" in str(exc)
    else:
        raise AssertionError("reindex accepted an invalid confirmation")
    try:
        rollback("wrong")
    except RuntimeError as exc:
        assert "--confirm ROLLBACK" in str(exc)
    else:
        raise AssertionError("rollback accepted an invalid confirmation")
