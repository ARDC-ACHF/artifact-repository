"""Tests for the service/index layer: reindex, long IRIs, storage round-trip."""

from __future__ import annotations

import json

from app.index import FtsIndex
from app.service import RepositoryService
from app.storage import build_storage
from app.storage.base import iri_to_key


def _service(settings) -> RepositoryService:
    storage = build_storage(settings)
    index = FtsIndex(settings.index_path)
    return RepositoryService(settings, storage, index)


def test_reindex_rebuilds_from_storage(settings, sample_artifacts):
    svc = _service(settings)
    for art in sample_artifacts.values():
        svc.publish(art)

    # Wipe the index and rebuild purely from storage (the source of truth).
    total_before, _ = svc.search("Beckett")
    assert total_before >= 4

    count = svc.reindex()
    assert count == len(sample_artifacts)

    total_after, results = svc.search("Beckett")
    assert total_after == total_before
    partners = {r.partner for r in results}
    assert {"ausstage", "austlit", "nga"}.issubset(partners)


def test_very_long_iri_roundtrips(settings):
    svc = _service(settings)
    long_iri = "https://ausstage.org.au/event/" + "x" * 500
    art = {
        "@context": "https://linked.art/ns/v1/linked-art.json",
        "id": long_iri,
        "type": "Activity",
        "_label": "A very long IRI performance",
    }
    resp = svc.publish(art)
    assert resp.id == long_iri
    # The encoded key must have been hashed to stay storage-safe.
    assert iri_to_key(long_iri).startswith("h_")
    # …but retrieval by the raw IRI still returns the exact bytes.
    body = svc.get_raw(long_iri)
    assert body is not None
    assert json.loads(body.decode("utf-8")) == art


def test_partner_fallback_slug(settings):
    svc = _service(settings)
    art = {
        "@context": "https://linked.art/ns/v1/linked-art.json",
        "id": "https://collections.example.museum/thing/1",
        "type": "HumanMadeObject",
        "_label": "Unknown partner object",
    }
    resp = svc.publish(art)
    # Fallback derives a slug from the domain, ignoring service subdomains.
    assert resp.partner == "example"
    assert svc.search("Unknown", partners=["example"])[0] == 1
