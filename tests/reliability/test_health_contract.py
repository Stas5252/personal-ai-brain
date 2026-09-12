"""Public liveness and protected readiness are distinct contracts."""
from fastapi.testclient import TestClient

from src.brain.api.app import app


def test_liveness_endpoint_is_public():
    response = TestClient(app).get('/health/live')
    assert response.status_code == 200
    assert response.json()['status'] == 'alive'


def test_readiness_endpoint_requires_api_key():
    response = TestClient(app).get('/health/ready')
    assert response.status_code == 401
