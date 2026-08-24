"""Snapshotting tests: versioned storage, service logic, and API endpoints.

All tests run against the local filesystem backend and a temporary SQLite
index (see ``conftest.py``), so no Swift/OpenStack access is required.
"""

from __future__ import annotations

import urllib.parse

import pytest


def _locator(iri: str) -> str:
    return f"/api/v1/artifacts/{urllib.parse.quote(iri, safe='')}"


# ---------------------------------------------------------------------------
# Storage layer (FilesystemStore) — versioned put/get/get_version/list_versions
# ---------------------------------------------------------------------------


@pytest.fixture
def store(settings):
    from app.storage.fs_store import FilesystemStore

    return FilesystemStore(settings)


def test_put_get_single_version(store):
    iri = "https://ausstage.org.au/event/1"
    store.put(iri, b'{"v":1}', partner="ausstage", type="Activity", label="v1",
              published_at="2024-05-01T10:00:00.000000Z")
    art = store.get(iri)
    assert art is not None
    assert art.body == b'{"v":1}'
    assert art.published_at == "2024-05-01T10:00:00.000000Z"
    assert art.partner == "ausstage"
    assert art.label == "v1"


def test_multi_version_get_returns_latest(store):
    iri = "https://ausstage.org.au/event/2"
    store.put(iri, b'{"v":1}', partner="ausstage", type="Activity", label="v1",
              published_at="2024-05-01T10:00:00.000000Z")
    store.put(iri, b'{"v":2}', partner="ausstage", type="Activity", label="v2",
              published_at="2024-05-08T09:15:00.123456Z")
    art = store.get(iri)
    assert art is not None
    assert art.body == b'{"v":2}'
    assert art.published_at == "2024-05-08T09:15:00.123456Z"


def test_get_version_returns_specific_snapshot(store):
    iri = "https://ausstage.org.au/event/3"
    store.put(iri, b'{"v":1}', partner="ausstage", type="Activity", label="v1",
              published_at="2024-05-01T10:00:00.000000Z")
    store.put(iri, b'{"v":2}', partner="ausstage", type="Activity", label="v2",
              published_at="2024-05-08T09:15:00.123456Z")
    old = store.get_version(iri, "2024-05-01T10:00:00.000000Z")
    assert old is not None
    assert old.body == b'{"v":1}'
    assert store.get_version(iri, "2999-01-01T00:00:00.000000Z") is None


def test_list_versions_newest_first_with_current_flag(store):
    iri = "https://ausstage.org.au/event/4"
    store.put(iri, b'{"v":1}', partner="ausstage", type="Activity", label="v1",
              published_at="2024-05-01T10:00:00.000000Z")
    store.put(iri, b'{"v":2}', partner="ausstage", type="Activity", label="v2",
              published_at="2024-05-08T09:15:00.123456Z")
    versions = store.list_versions(iri)
    assert [v.published_at for v in versions] == [
        "2024-05-08T09:15:00.123456Z",
        "2024-05-01T10:00:00.000000Z",
    ]
    assert versions[0].is_current is True
    assert versions[1].is_current is False
    assert store.list_versions("https://unknown.example/x") == []


def test_restore_pointer_rolls_back_current(store):
    iri = "https://ausstage.org.au/event/5"
    store.put(iri, b'{"v":1}', partner="ausstage", type="Activity", label="v1",
              published_at="2024-05-01T10:00:00.000000Z")
    store.put(iri, b'{"v":2}', partner="ausstage", type="Activity", label="v2",
              published_at="2024-05-08T09:15:00.123456Z")
    # Simulate rollback of the second publish.
    store.restore_pointer(iri, "2024-05-01T10:00:00.000000Z")
    store.delete_version(iri, "2024-05-08T09:15:00.123456Z")
    art = store.get(iri)
    assert art is not None
    assert art.body == b'{"v":1}'
    assert [v.published_at for v in store.list_versions(iri)] == [
        "2024-05-01T10:00:00.000000Z"
    ]


def test_get_falls_back_to_newest_when_pointer_missing(store, settings):
    iri = "https://ausstage.org.au/event/6"
    store.put(iri, b'{"v":1}', partner="ausstage", type="Activity", label="v1",
              published_at="2024-05-01T10:00:00.000000Z")
    store.put(iri, b'{"v":2}', partner="ausstage", type="Activity", label="v2",
              published_at="2024-05-08T09:15:00.123456Z")
    # Remove the pointer entirely: get() should still resolve the newest version.
    store.restore_pointer(iri, None)
    art = store.get(iri)
    assert art is not None
    assert art.body == b'{"v":2}'


def test_list_returns_only_current_versions(store):
    iri = "https://ausstage.org.au/event/7"
    store.put(iri, b'{"v":1}', partner="ausstage", type="Activity", label="v1",
              published_at="2024-05-01T10:00:00.000000Z")
    store.put(iri, b'{"v":2}', partner="ausstage", type="Activity", label="v2",
              published_at="2024-05-08T09:15:00.123456Z")
    entries = store.list()
    matching = [e for e in entries if e.iri == iri]
    assert len(matching) == 1
    assert matching[0].label == "v2"


# ---------------------------------------------------------------------------
# Service layer (RepositoryService) — change-triggered snapshotting
# ---------------------------------------------------------------------------


@pytest.fixture
def service(settings):
    from app.index import FtsIndex
    from app.service import RepositoryService
    from app.storage import build_storage

    return RepositoryService(
        settings, build_storage(settings), FtsIndex(settings.index_path)
    )


def _activity(iri: str, label: str) -> dict:
    return {
        "@context": "https://linked.art/ns/v1/linked-art.json",
        "id": iri,
        "type": "Activity",
        "_label": label,
    }


def test_publish_first_version(service):
    iri = "https://ausstage.org.au/event/900"
    resp = service.publish(_activity(iri, "Godot, 1957"))
    assert resp.version_created is True
    assert resp.snapshot_of is None
    assert resp.published_at
    hist = service.list_versions(iri)
    assert hist is not None
    assert hist.total == 1
    assert hist.versions[0].is_current is True


def test_changed_republish_creates_snapshot(service):
    iri = "https://ausstage.org.au/event/901"
    r1 = service.publish(_activity(iri, "Godot, 1957"))
    r2 = service.publish(_activity(iri, "Godot (Arts Theatre), 1957"))
    assert r2.version_created is True
    assert r2.snapshot_of == r1.published_at
    assert r2.published_at != r1.published_at

    hist = service.list_versions(iri)
    assert hist.total == 2
    # Newest first, only the newest is current.
    assert hist.versions[0].published_at == r2.published_at
    assert hist.versions[0].is_current is True
    assert hist.versions[1].published_at == r1.published_at
    assert hist.versions[1].is_current is False

    # Both versions retrievable verbatim.
    old = service.get_version_raw(iri, r1.published_at)
    new = service.get_version_raw(iri, r2.published_at)
    assert b"Godot, 1957" in old
    assert b"Arts Theatre" in new
    # Current get returns the newest.
    assert b"Arts Theatre" in service.get_raw(iri)


def test_idempotent_republish_is_noop(service):
    iri = "https://ausstage.org.au/event/902"
    art = _activity(iri, "Godot, 1957")
    r1 = service.publish(art)
    # Same content, different key ordering -> still a no-op (canonical compare).
    reordered = {"_label": "Godot, 1957", "type": "Activity",
                 "id": iri, "@context": art["@context"]}
    r2 = service.publish(reordered)
    assert r2.version_created is False
    assert r2.published_at == r1.published_at
    hist = service.list_versions(iri)
    assert hist.total == 1


def test_search_excludes_snapshots(service):
    iri = "https://ausstage.org.au/event/903"
    service.publish(_activity(iri, "Godot, 1957"))
    service.publish(_activity(iri, "Godot (Arts Theatre), 1957"))
    total, results = service.search("Godot", partners=["ausstage"])
    matching = [r for r in results if r.id == iri]
    assert len(matching) == 1  # one current hit, not one-per-version
    assert "Arts Theatre" in matching[0].label


def test_index_failure_rolls_back_version(settings):
    from app.index import FtsIndex
    from app.service import RepositoryService
    from app.storage import build_storage

    storage = build_storage(settings)
    iri = "https://ausstage.org.au/event/904"

    # First publish succeeds with a working index.
    good = RepositoryService(settings, storage, FtsIndex(settings.index_path))
    r1 = good.publish(_activity(iri, "Godot, 1957"))

    # Second publish uses an index that always fails on upsert.
    class BoomIndex(FtsIndex):
        def upsert(self, *a, **k):  # type: ignore[override]
            raise RuntimeError("boom")

    boom = RepositoryService(settings, storage, BoomIndex(settings.index_path))
    with pytest.raises(RuntimeError):
        boom.publish(_activity(iri, "Godot (Arts Theatre), 1957"))

    # Rollback: pointer restored to v1, the failed version removed.
    current = storage.get(iri)
    assert current.published_at == r1.published_at
    assert b"Godot, 1957" in current.body
    assert [v.published_at for v in storage.list_versions(iri)] == [r1.published_at]


def test_snapshots_retained_after_several_updates(service):
    iri = "https://ausstage.org.au/event/905"
    published = []
    for i in range(4):
        r = service.publish(_activity(iri, f"Godot revision {i}"))
        published.append(r.published_at)
    hist = service.list_versions(iri)
    assert hist.total == 4
    # Every earlier snapshot remains retrievable verbatim.
    for i, pa in enumerate(published):
        body = service.get_version_raw(iri, pa)
        assert body is not None
        assert f"revision {i}".encode() in body


# ---------------------------------------------------------------------------
# API layer (FastAPI TestClient) — publish response + version endpoints
# ---------------------------------------------------------------------------


def test_publish_response_includes_version_fields(client):
    iri = "https://ausstage.org.au/event/1000"
    r1 = client.post("/api/v1/artifacts", json=_activity(iri, "Godot, 1957"))
    assert r1.status_code == 201, r1.text
    b1 = r1.json()
    assert b1["version_created"] is True
    assert b1["snapshot_of"] is None
    assert b1["published_at"]

    # Changed re-publish -> new version referencing the prior published_at.
    r2 = client.post("/api/v1/artifacts", json=_activity(iri, "Godot (rev), 1957"))
    b2 = r2.json()
    assert b2["version_created"] is True
    assert b2["snapshot_of"] == b1["published_at"]

    # Idempotent re-publish -> no new version.
    r3 = client.post("/api/v1/artifacts", json=_activity(iri, "Godot (rev), 1957"))
    b3 = r3.json()
    assert b3["version_created"] is False


def test_versions_endpoint_lists_history(client):
    iri = "https://ausstage.org.au/event/1001"
    client.post("/api/v1/artifacts", json=_activity(iri, "Godot, 1957"))
    client.post("/api/v1/artifacts", json=_activity(iri, "Godot (rev), 1957"))

    r = client.get(f"{_locator(iri)}/versions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == iri
    assert body["total"] == 2
    assert body["versions"][0]["is_current"] is True
    assert body["versions"][1]["is_current"] is False


def test_versions_endpoint_unknown_iri_404(client):
    r = client.get(f"{_locator('https://unknown.example/x')}/versions")
    assert r.status_code == 404


def test_get_specific_version_verbatim(client):
    iri = "https://ausstage.org.au/event/1002"
    client.post("/api/v1/artifacts", json=_activity(iri, "Godot, 1957"))
    client.post("/api/v1/artifacts", json=_activity(iri, "Godot (rev), 1957"))

    versions = client.get(f"{_locator(iri)}/versions").json()["versions"]
    older = versions[1]  # not current
    r = client.get(older["locator"])
    assert r.status_code == 200, r.text
    assert r.headers.get("X-Published-At") == older["published_at"]
    assert "Godot, 1957" in r.text
    assert "rev" not in r.json()["_label"]


def test_get_specific_version_unknown_404(client):
    iri = "https://ausstage.org.au/event/1003"
    client.post("/api/v1/artifacts", json=_activity(iri, "Godot, 1957"))
    bad = urllib.parse.quote("2999-01-01T00:00:00.000000Z", safe="")
    r = client.get(f"{_locator(iri)}/versions/{bad}")
    assert r.status_code == 404


def test_current_retrieval_sets_published_at_header(client):
    iri = "https://ausstage.org.au/event/1004"
    pub = client.post("/api/v1/artifacts", json=_activity(iri, "Godot, 1957")).json()
    r = client.get(_locator(iri))
    assert r.status_code == 200
    assert r.headers.get("X-Published-At") == pub["published_at"]
