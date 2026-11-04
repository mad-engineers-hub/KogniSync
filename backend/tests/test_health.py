from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_basic_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["project"] == "KogniSync"


def test_db_connectivity_endpoint():
    response = client.get("/health/db")
    if response.status_code == 503:
        import pytest
        pytest.skip("PostgreSQL database unreachable on localhost:5434")
    assert response.status_code == 200
    data = response.json()
    assert data["database"] == "healthy"
    assert data["engine"] == "postgresql"
    assert data["port"] == 5434


def test_redis_connectivity_endpoint():
    response = client.get("/health/redis")
    if response.status_code == 503:
        import pytest
        pytest.skip("Redis service unreachable on localhost:6380")
    assert response.status_code == 200
    data = response.json()
    assert data["redis"] == "healthy"
    assert data["port"] == 6380
