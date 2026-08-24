"""API tests for retrieval, listing, and cross-domain search (fs backend)."""

from __future__ import annotations

import json
import urllib.parse


def _locator(iri: str) -> str:
    return f"/api/v1/artifacts/{urllib.parse.quote(iri, safe='')}"


def _publish_all(client, sample_artifacts) -> None:
    for art in sample_artifacts.values():
        r = client.post("/api/v1/artifacts", json=art)
        assert r.status_code == 201, r.text


def test_retrieve_roundtrips_verbatim(client, sample_artifacts):
    art = sample_artifacts["ausstage_event_12345"]
    client.post("/api/v1/artifacts", json=art)

    r = client.get(_locator(art["id"]))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/ld+json")
    assert json.loads(r.content) == art


def test_retrieve_missing_returns_404(client):
    r = client.get(_locator("https://ausstage.org.au/event/does-not-exist"))
    assert r.status_code == 404


def test_list_and_filter_by_partner_and_type(client, sample_artifacts):
    _publish_all(client, sample_artifacts)

    r = client.get("/api/v1/artifacts")
    assert r.status_code == 200
    assert r.json()["total"] == len(sample_artifacts)

    r = client.get("/api/v1/artifacts", params={"partner": "nga"})
    assert r.status_code == 200
    partners = {row["partner"] for row in r.json()["results"]}
    assert partners == {"nga"}

    r = client.get("/api/v1/artifacts", params={"type": "Activity"})
    types = {row["type"] for row in r.json()["results"]}
    assert types == {"Activity"}


def test_cross_domain_search_returns_mixed_results(client, sample_artifacts):
    _publish_all(client, sample_artifacts)

    r = client.get("/api/v1/search", params={"q": "Beckett"})
    assert r.status_code == 200
    body = r.json()
    # Beckett appears in performance, literature, art and person artifacts.
    types = {row["type"] for row in body["results"]}
    partners = {row["partner"] for row in body["results"]}
    assert {"Activity", "LinguisticObject", "HumanMadeObject"}.issubset(types)
    assert {"ausstage", "austlit", "nga"}.issubset(partners)
    assert body["total"] >= 4


def test_search_type_filter_narrows(client, sample_artifacts):
    _publish_all(client, sample_artifacts)

    r = client.get(
        "/api/v1/search", params={"q": "Beckett", "type": "HumanMadeObject"}
    )
    assert r.status_code == 200
    types = {row["type"] for row in r.json()["results"]}
    assert types == {"HumanMadeObject"}


def test_search_partner_filter_narrows(client, sample_artifacts):
    _publish_all(client, sample_artifacts)

    r = client.get("/api/v1/search", params={"q": "Beckett", "partner": "austlit"})
    assert r.status_code == 200
    partners = {row["partner"] for row in r.json()["results"]}
    assert partners == {"austlit"}


def test_search_repeatable_filters(client, sample_artifacts):
    _publish_all(client, sample_artifacts)

    r = client.get(
        "/api/v1/search",
        params=[("q", "Beckett"), ("partner", "austlit"), ("partner", "nga")],
    )
    assert r.status_code == 200
    partners = {row["partner"] for row in r.json()["results"]}
    assert partners == {"austlit", "nga"}


def test_search_result_locator_resolves(client, sample_artifacts):
    _publish_all(client, sample_artifacts)

    r = client.get("/api/v1/search", params={"q": "Sunflowers"})
    results = r.json()["results"]
    assert results, "expected at least one result"
    loc = results[0]["locator"]
    got = client.get(loc)
    assert got.status_code == 200
