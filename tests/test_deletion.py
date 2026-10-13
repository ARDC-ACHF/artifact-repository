"""Deletion contract across filesystem, simulated Swift and authenticated HTTP."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.auth import BasicAuthProvider
from app.index import FtsIndex
from app.main import create_app
from app.service import RepositoryService
from app.storage.fs_store import FilesystemStore
from app.storage.swift_store import SwiftStore
from app.validation.validator import CONTEXT_URL
from test_storage import MemorySwift


@pytest.fixture(params=["fs", "swift"])
def resources(request, tmp_path):
    store = (FilesystemStore(tmp_path / "artifacts") if request.param == "fs"
             else SwiftStore(MemorySwift(), "artifacts"))
    index = FtsIndex(tmp_path / "index.sqlite")
    yield RepositoryService(store, index), store, index
    index.close()


@pytest.fixture
def payload():
    return {"@context": CONTEXT_URL, "id": "https://example.org/作品?x=+%2F&y=1#part",
            "type": "HumanMadeObject", "_label": "Blue painting"}


def test_delete_history_current_and_last(resources, payload):
    service, store, index = resources
    iri = payload["id"]
    first = service.publish(payload)
    middle = service.publish({**payload, "_label": "Green painting"})
    latest = service.publish({**payload, "_label": "Red painting"})
    assert service.delete_version(iri, middle.published_at)
    assert store.get_version(iri, middle.published_at) is None
    assert service.search("Red")[0] == 1
    assert service.delete_version(iri, latest.published_at)
    assert json.loads(service.get_raw(iri)) == payload
    assert store.get(iri).published_at == first.published_at
    assert service.search("Blue")[0] == 1
    assert service.search("Red")[0] == 0
    assert service.list_versions(iri).total == 1
    assert service.delete_version(iri, first.published_at)
    assert store.get(iri) is None
    assert store.list_versions(iri) == []
    assert index.count() == 0
    assert not service.delete_version(iri, first.published_at)
    assert not service.delete(iri)


def test_delete_artifact_isolated_and_republish(resources, payload):
    service, store, index = resources
    first = service.publish(payload)
    service.publish({**payload, "_label": "Red painting"})
    other = {**payload, "id": "https://example.org/other"}
    service.publish(other)
    assert service.delete(payload["id"])
    assert store.get(payload["id"]) is None
    assert store.list_versions(payload["id"]) == []
    assert service.get_version_raw(payload["id"], first.published_at) is None
    assert service.list()[0] == 1
    assert json.loads(service.get_raw(other["id"])) == other
    assert service.reindex() == 1
    assert service.publish(payload).version_created
    assert service.list_versions(payload["id"]).total == 1


@pytest.mark.parametrize("operation", ["all", "current", "last"])
def test_index_failure_does_not_delete(resources, payload, monkeypatch, operation):
    service, store, index = resources
    latest = service.publish(payload)
    if operation == "current":
        latest = service.publish({**payload, "_label": "Red painting"})
    before = store.get(payload["id"])
    versions = store.list_versions(payload["id"])

    def fail(*args, **kwargs):
        raise RuntimeError("index unavailable")

    monkeypatch.setattr(index, "upsert" if operation == "current" else "delete", fail)
    with pytest.raises(RuntimeError, match="index unavailable"):
        if operation == "all":
            service.delete(payload["id"])
        else:
            service.delete_version(payload["id"], latest.published_at)
    assert store.get(payload["id"]) == before
    assert store.list_versions(payload["id"]) == versions


def test_snapshot_failure_restores_pointer_and_search(resources, payload, monkeypatch):
    service, store, index = resources
    service.publish(payload)
    latest = service.publish({**payload, "_label": "Red painting"})

    def fail(*args):
        raise OSError("storage unavailable")

    monkeypatch.setattr(store, "delete_version", fail)
    with pytest.raises(OSError, match="storage unavailable"):
        service.delete_version(payload["id"], latest.published_at)
    assert store.get(payload["id"]).published_at == latest.published_at
    assert service.search("Red")[0] == 1
    assert service.search("Blue")[0] == 0


def test_partial_artifact_failure_can_be_retried(resources, payload, monkeypatch):
    service, store, index = resources
    service.publish(payload)
    latest = service.publish({**payload, "_label": "Red painting"})
    original = store.delete

    def partial(iri):
        store.restore_pointer(iri, None)
        store.delete_version(iri, latest.published_at)
        raise OSError("partial deletion")

    monkeypatch.setattr(store, "delete", partial)
    with pytest.raises(OSError, match="partial deletion"):
        service.delete(payload["id"])
    assert service.list()[0] == 0
    assert len(store.list_versions(payload["id"])) == 1
    monkeypatch.setattr(store, "delete", original)
    assert service.delete(payload["id"])
    assert store.list_versions(payload["id"]) == []


def test_promotes_newest_remaining_metadata(resources, payload):
    service, store, index = resources
    service.publish(payload)
    middle_payload = {**payload, "type": "Person", "_label": "Green person"}
    middle = service.publish(middle_payload)
    latest = service.publish({**payload, "_label": "Red painting"})
    assert service.delete_version(payload["id"], latest.published_at)
    assert store.get(payload["id"]).published_at == middle.published_at
    assert json.loads(service.get_raw(payload["id"])) == middle_payload
    assert service.list(type="Person")[0] == 1
    assert service.list(type="HumanMadeObject")[0] == 0
    assert service.search("Green")[0] == 1
    assert service.list_versions(payload["id"]).total == 2


def test_ambiguous_snapshot_delete_keeps_surviving_pointer(resources, payload, monkeypatch):
    service, store, index = resources
    first = service.publish(payload)
    latest = service.publish({**payload, "_label": "Red painting"})
    original = store.delete_version

    def deleted_then_failed(iri, stamp):
        original(iri, stamp)
        raise OSError("response lost")

    monkeypatch.setattr(store, "delete_version", deleted_then_failed)
    with pytest.raises(OSError, match="response lost"):
        service.delete_version(payload["id"], latest.published_at)
    assert store.get(payload["id"]).published_at == first.published_at
    assert store.get_version(payload["id"], latest.published_at) is None
    assert service.search("Blue")[0] == 1
    assert not service.delete_version(payload["id"], latest.published_at)


def test_concurrent_publish_and_delete(resources, payload):
    service, store, index = resources

    def mutate(i):
        if i % 2:
            service.delete(payload["id"])
        else:
            service.publish({**payload, "_label": str(i)})

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(mutate, range(20)))
    current = store.get(payload["id"])
    assert index.count() == int(current is not None)
    if current is not None:
        assert service.list()[1][0].label == current.label
        assert sum(v.is_current for v in store.list_versions(payload["id"])) == 1
    else:
        assert store.list_versions(payload["id"]) == []


def test_deletion_persists_after_restart(tmp_path, payload):
    providers = (BasicAuthProvider("tester", "secret"),)
    with TestClient(create_app(data_dir=tmp_path, auth_providers=providers)) as client:
        client.auth = ("tester", "secret")
        first = client.post("/api/v1/artifacts", json=payload).json()
        latest = client.post("/api/v1/artifacts", json={**payload, "_label": "Red painting"}).json()
        assert client.delete(latest["stored_at"]).status_code == 200
    with TestClient(create_app(data_dir=tmp_path, auth_providers=providers)) as client:
        client.auth = ("tester", "secret")
        assert client.get(first["locator"]).json() == payload
        assert client.get(latest["stored_at"]).status_code == 404
        assert client.delete(first["locator"]).status_code == 200
    with TestClient(create_app(data_dir=tmp_path, auth_providers=providers)) as client:
        client.auth = ("tester", "secret")
        assert client.get(first["stored_at"]).status_code == 404
        assert client.get("/api/v1/artifacts").json()["total"] == 0


def test_deletion_fails_closed(tmp_path):
    with TestClient(create_app(data_dir=tmp_path, auth_providers=())) as client:
        for path in ["item", "version"]:
            assert client.delete("/api/v1/artifacts/" + path).status_code == 503
    assert list(tmp_path.iterdir()) == []


def test_deletion_http(resources, payload):
    service, store, index = resources
    with TestClient(create_app(service=service, auth_providers=(BasicAuthProvider("tester", "secret"),))) as client:
        first = service.publish(payload)
        latest = service.publish({**payload, "_label": "Red painting"})
        for url in [first.locator, latest.stored_at]:
            assert client.delete(url).status_code == 401
        assert len(store.list_versions(payload["id"])) == 2
        client.auth = ("tester", "secret")
        response = client.delete(latest.stored_at)
        assert response.status_code == 200
        assert response.json() == {"id": payload["id"], "deleted": True, "published_at": latest.published_at}
        assert client.get(first.locator).json() == payload
        assert client.get(latest.stored_at).status_code == 404
        assert client.delete(latest.stored_at).status_code == 404
        assert client.delete(first.locator).json() == {"id": payload["id"], "deleted": True}
        assert client.get(first.locator).status_code == 404
        assert client.get("/api/v1/artifacts").json()["total"] == 0
        assert client.get("/api/v1/search", params={"q": "painting"}).json()["total"] == 0
        assert client.delete(first.locator).status_code == 404
        for path, params in [("item", {}), ("item", {"iri": " "}),
                             ("version", {"iri": payload["id"]}),
                             ("version", {"iri": payload["id"], "published_at": "bad"})]:
            assert client.delete("/api/v1/artifacts/" + path, params=params).status_code == 422
        paths = client.get("/openapi.json").json()["paths"]
        for path in ["item", "version"]:
            operation = paths["/api/v1/artifacts/" + path]["delete"]
            assert operation["security"] == [{"Basic": []}]
            assert {"200", "404", "422", "401", "503"} <= operation["responses"].keys()