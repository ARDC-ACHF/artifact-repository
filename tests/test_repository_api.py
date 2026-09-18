"""End-to-end repository checks using real local storage and SQLite."""

import socket

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.auth import BasicAuthProvider
from app.validation.validator import CONTEXT_URL


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Repository tests must not use external services")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_dir=tmp_path, auth_providers=(BasicAuthProvider("tester", "test-secret"),))) as client:
        client.auth = ("tester", "test-secret")
        yield client


@pytest.fixture
def payload():
    return {"@context": CONTEXT_URL, "id": "https://nga.gov.au/object/1",
            "type": "HumanMadeObject", "_label": "Golden landscape"}


def test_publish_retrieve_update_history(client, payload):
    first = client.post("/api/v1/artifacts", json=payload)
    assert first.status_code == 201
    result = first.json()
    assert result["partner"] == "nga"
    assert result["version_created"] is True
    assert result["snapshot_of"] is None
    assert first.headers["location"] == result["locator"]
    current = client.get(result["locator"])
    assert current.headers["content-type"] == "application/ld+json"
    assert current.json() == payload
    assert client.get(result["stored_at"]).json() == payload

    retry = client.post("/api/v1/artifacts", json=dict(reversed(list(payload.items()))))
    assert retry.status_code == 200
    assert retry.json()["version_created"] is False
    assert retry.json()["published_at"] == result["published_at"]
    payload["_label"] = "Silver portrait"
    updated = client.post("/api/v1/artifacts", json=payload)
    assert updated.status_code == 201
    assert updated.json()["snapshot_of"] == result["published_at"]
    assert client.get(result["locator"]).json() == payload
    assert client.get(result["stored_at"]).json()["_label"] == "Golden landscape"
    history = client.get("/api/v1/artifacts/versions", params={"iri": payload["id"]}).json()
    assert history["total"] == 2
    assert [v["is_current"] for v in history["versions"]] == [True, False]
    assert all(client.get(v["locator"]).status_code == 200 for v in history["versions"])
    assert client.get("/api/v1/search", params={"q": "Golden"}).json()["total"] == 0
    assert client.get("/api/v1/search", params={"q": "Silver"}).json()["total"] == 1


@pytest.mark.parametrize("iri", [
    "https://example.org/a/versions/b?x=1&y=%2F#片", "relative-id", "https://example.org/a+b%252F",
])
def test_locator_round_trip(client, payload, iri):
    payload["id"] = iri
    response = client.post("/api/v1/artifacts", json=payload)
    assert response.status_code == 201
    for key in ["locator", "stored_at"]:
        assert client.get(response.json()[key]).json() == payload


@pytest.mark.parametrize("body", ["{", "null", "[]", '"text"', "NaN", "{}", b"\xff"])
def test_invalid_publication_never_listed(client, body):
    response = client.post("/api/v1/artifacts", content=body)
    assert response.status_code == 422
    assert response.json()["valid"] is False
    assert response.json()["errors"]
    assert client.get("/api/v1/artifacts").json()["total"] == 0


def test_filters_and_paging(client, payload):
    for host, type_, label in [("nga.gov.au", "HumanMadeObject", "Shared painting"),
                               ("ausstage.org.au", "Activity", "Shared performance"),
                               ("austlit.edu.au", "LinguisticObject", "Shared novel")]:
        payload.update(id=f"https://{host}/1", type=type_, _label=label)
        assert client.post("/api/v1/artifacts", json=payload).status_code == 201
    listing = client.get("/api/v1/artifacts", params={"limit": 1, "offset": 1}).json()
    assert listing["total"] == 3 and len(listing["results"]) == 1
    for params in [{"partner": "nga"}, {"type": "Activity"}]:
        assert client.get("/api/v1/artifacts", params=params).json()["total"] == 1
    search = client.get("/api/v1/search", params=[("q", "Shar"), ("partners", "nga"),
                                                ("partners", "ausstage"), ("limit", 1)]).json()
    assert search["total"] == 2 and len(search["results"]) == 1
    assert client.get("/api/v1/search", params={"q": "Shared", "types": "Activity"}).json()["total"] == 1


@pytest.mark.parametrize("path,params,status", [
    ("artifacts/item", {"iri": "missing"}, 404),
    ("artifacts/versions", {"iri": "missing"}, 404),
    ("artifacts/version", {"iri": "missing", "published_at": "2026-09-18T00:00:00.000000Z"}, 404),
    ("artifacts/version", {"iri": "missing", "published_at": "bad"}, 422),
    ("artifacts", {"limit": 0}, 422), ("artifacts", {"offset": -1}, 422),
    ("search", {"q": "test", "limit": 201}, 422), ("search", {}, 422),
    ("artifacts/item", {"iri": " "}, 422),
])
def test_request_errors(client, path, params, status):
    assert client.get("/api/v1/" + path, params=params).status_code == status


def test_restart_keeps_artifacts_and_index(tmp_path, payload):
    with TestClient(create_app(data_dir=tmp_path, auth_providers=(BasicAuthProvider("tester", "test-secret"),))) as client:
        client.auth = ("tester", "test-secret")
        result = client.post("/api/v1/artifacts", json=payload).json()
    with TestClient(create_app(data_dir=tmp_path, auth_providers=(BasicAuthProvider("tester", "test-secret"),))) as client:
        client.auth = ("tester", "test-secret")
        assert client.get(result["locator"]).json() == payload
        assert client.get("/api/v1/search", params={"q": "landscape"}).json()["total"] == 1


def test_openapi_repository_contract(client):
    paths = client.get("/openapi.json").json()["paths"]
    operation = paths["/api/v1/artifacts"]["post"]
    assert set(operation["responses"]) >= {"200", "201", "422"}
    assert "application/json" in operation["requestBody"]["content"]