"""
Tests for Knowledge REST API Endpoints.
Covers source upload, listing, details, status, hybrid search, reprocessing, and stats.
"""
import pytest
from fastapi.testclient import TestClient
from src.brain.api.app import app

@pytest.fixture
def client():
    return TestClient(app, headers={"Authorization": "Bearer test-brain-key"})


def test_api_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["service"] == "Personal AI Brain"


def test_api_knowledge_stats(client):
    res = client.get("/knowledge/stats")
    assert res.status_code == 200
    data = res.json()
    assert "total_sources" in data
    assert "total_chunks" in data
    assert "by_layer" in data
    assert "vector_index_count" in data


def test_api_create_and_delete_source(client):
    # 1. Create text source
    payload = {
        "title": "API Test Rules",
        "content": "Правила студии: курение запрещено, сменная обувь обязательна.",
        "layer": "professional",
        "author": "Manager"
    }
    create_res = client.post("/knowledge/sources", data=payload)
    assert create_res.status_code == 200
    res_data = create_res.json()
    source_id = res_data["source"]["source_id"]
    assert res_data["chunks_count"] > 0

    # 2. Get source detail
    detail_res = client.get(f"/knowledge/sources/{source_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["source"]["title"] == "API Test Rules"
    assert len(detail["chunks"]) > 0

    # 3. Check status endpoint
    status_res = client.get(f"/knowledge/sources/{source_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "COMPLETED"

    # 4. Search for the chunk
    search_payload = {
        "query": "сменная обувь в студии",
        "limit": 3
    }
    search_res = client.post("/knowledge/search", json=search_payload)
    assert search_res.status_code == 200
    hits = search_res.json()["results"]
    assert len(hits) > 0
    assert any("сменная обувь" in h["chunk"]["content"] for h in hits)

    # 5. Delete source
    del_res = client.delete(f"/knowledge/sources/{source_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # 6. Verify 404 after deletion
    get_again = client.get(f"/knowledge/sources/{source_id}")
    assert get_again.status_code == 404
