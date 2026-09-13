"""Queued knowledge API contract tests."""
import os

import pytest
from fastapi.testclient import TestClient

from src.brain.api.app import app
from src.brain.knowledge.queue.ingestion_queue import IngestionQueue


@pytest.fixture(autouse=True)
def isolated_queue():
    IngestionQueue().clear()
    yield
    IngestionQueue().clear()


@pytest.fixture
def client():
    key = os.environ.get("BRAIN_API_KEY", "regression-only-not-a-production-key-0001")
    return TestClient(app, headers={"Authorization": f"Bearer {key}"})


def test_api_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "Personal AI Brain"


def test_api_knowledge_stats(client):
    response = client.get("/knowledge/stats")
    assert response.status_code == 200
    data = response.json()
    assert {"total_sources", "total_chunks", "by_layer", "by_status", "queue"} <= data.keys()


def test_text_registration_returns_canonical_job_contract(client):
    response = client.post("/knowledge/sources", data={
        "title": "API Test Rules", "content": "# Правила\n\nСменная обувь обязательна.",
        "layer": "professional", "author": "Manager",
    })
    assert response.status_code == 202
    body = response.json()
    assert response.headers["location"] == body["status_url"]
    assert body["status"] == "DISCOVERED"
    assert body["progress"] == 0.0
    job = client.get(body["status_url"])
    assert job.status_code == 200
    contract = job.json()
    assert contract["job_id"] == body["job_id"]
    assert contract["source_id"] == body["source_id"]
    assert contract["status"] == "DISCOVERED"
    assert contract["terminal"] is False
    detail = client.get(f"/knowledge/sources/{body['source_id']}")
    assert detail.status_code == 200
    assert detail.json()["source"]["status"] == "DISCOVERED"
    assert detail.json()["chunks"] == []


def test_duplicate_registration_reuses_active_job(client):
    payload = {"title": "Same", "content": "# Same\n\nAtomic duplicate registration."}
    first = client.post("/knowledge/sources", data=payload)
    second = client.post("/knowledge/sources", data=payload)
    assert first.status_code == second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["source_id"] == first.json()["source_id"]
    assert second.json()["duplicate"] is True
