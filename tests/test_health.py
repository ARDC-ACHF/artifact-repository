"""Smoke tests for the standalone API foundation."""

from fastapi.testclient import TestClient

from app.main import app, create_app


def test_health():
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_documentation():
    with TestClient(app) as client:
        docs = client.get("/docs")
        schema = client.get("/openapi.json")

    assert docs.status_code == 200
    assert "text/html" in docs.headers["content-type"]
    assert schema.status_code == 200
    assert "/health" in schema.json()["paths"]