"""API tests for publish + dry-run validation (fs backend)."""

from __future__ import annotations

import urllib.parse


def _locator(iri: str) -> str:
    return f"/api/v1/artifacts/{urllib.parse.quote(iri, safe='')}"


def test_publish_activity_returns_201_with_locator(client, sample_artifacts):
    art = sample_artifacts["ausstage_event_12345"]
    r = client.post("/api/v1/artifacts", json=art)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] == art["id"]
    assert body["partner"] == "ausstage"
    assert body["type"] == "Activity"
    assert body["locator"] == _locator(art["id"])


def test_publish_each_domain(client, sample_artifacts):
    expected = {
        "ausstage_event_12345": ("ausstage", "Activity"),
        "austlit_work_5551": ("austlit", "LinguisticObject"),
        "nga_object_98765": ("nga", "HumanMadeObject"),
    }
    for stem, (partner, type_) in expected.items():
        r = client.post("/api/v1/artifacts", json=sample_artifacts[stem])
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["partner"] == partner
        assert body["type"] == type_


def test_publish_invalid_returns_422_structured(client):
    r = client.post(
        "/api/v1/artifacts",
        json={"@context": "https://linked.art/ns/v1/linked-art.json", "type": "Activity"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["valid"] is False
    codes = {e["code"] for e in body["errors"]}
    assert "missing_field" in codes


def test_publish_unsupported_type_422(client):
    r = client.post(
        "/api/v1/artifacts",
        json={
            "@context": "https://linked.art/ns/v1/linked-art.json",
            "id": "https://example.org/x",
            "type": "Painting",
        },
    )
    assert r.status_code == 422
    codes = {e["code"] for e in r.json()["errors"]}
    assert "unsupported_type" in codes


def test_validate_endpoint_does_not_store(client, sample_artifacts):
    art = sample_artifacts["nga_object_98765"]
    r = client.post("/api/v1/artifacts/validate", json=art)
    assert r.status_code == 200
    assert r.json() == {"valid": True, "errors": []}
    # Nothing should have been stored: retrieval must 404.
    r2 = client.get(_locator(art["id"]))
    assert r2.status_code == 404


def test_validate_endpoint_invalid_422(client):
    r = client.post("/api/v1/artifacts/validate", json={"id": "x"})
    assert r.status_code == 422
    assert r.json()["valid"] is False


def test_duplicate_publish_is_upsert(client, sample_artifacts):
    art = sample_artifacts["austlit_work_5551"]
    r1 = client.post("/api/v1/artifacts", json=art)
    assert r1.status_code == 201
    # Publish again with an updated label.
    updated = dict(art)
    updated["_label"] = "Waiting for Godot (revised edition)"
    r2 = client.post("/api/v1/artifacts", json=updated)
    assert r2.status_code == 201
    # Only one index entry should exist for this IRI.
    s = client.get("/api/v1/search", params={"q": "Godot", "partner": "austlit"})
    if s.status_code == 200:  # search implemented in a later step
        ids = [row["id"] for row in s.json()["results"]]
        assert ids.count(art["id"]) == 1
