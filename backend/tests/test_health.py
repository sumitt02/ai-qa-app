"""Smoke tests for the app."""


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_schema(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "paths" in response.json()
