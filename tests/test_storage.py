"""Shared storage contract; Swift is simulated, not a live-service test."""

import socket

import pytest
from swiftclient.exceptions import ClientException

from app.storage.base import VersionConflictError, iri_to_key
from app.storage.fs_store import FilesystemStore
from app.storage.swift_store import SwiftStore

IRI = "https://example.org/作品/1"
V1 = "2026-09-18T01:00:00.000000Z"
V2 = "2026-09-18T02:00:00.000000Z"
BODY = b'{ "id": "example", "type": "Person" }\n'


class MemorySwift:
    """Model object operations, conditional creation and HTTP failures."""

    def __init__(self):
        self.objects = {}
        self.failure = None

    def check(self):
        if self.failure:
            raise ClientException("Injected failure", http_status=self.failure)

    def put_container(self, container):
        self.check()

    def head_container(self, container):
        self.check()
        return {}

    def put_object(self, container, name, contents, headers=None):
        self.check()
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        if headers.get("if-none-match") == "*" and name in self.objects:
            raise ClientException("Exists", http_status=412)
        assert isinstance(contents, bytes)
        for value in headers.values():
            value.encode("ascii")
        self.objects[name] = (headers, contents)

    def get_object(self, container, name):
        self.check()
        if name not in self.objects:
            raise ClientException("Missing", http_status=404)
        return self.objects[name]

    def head_object(self, container, name):
        return self.get_object(container, name)[0]

    def delete_object(self, container, name):
        self.get_object(container, name)
        del self.objects[name]

    def get_container(self, container, prefix="", full_listing=False):
        self.check()
        assert full_listing is True
        return {}, [{"name": name} for name in sorted(self.objects) if name.startswith(prefix)]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Storage unit tests must not use the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture(params=["fs", "swift"])
def store(request, tmp_path):
    if request.param == "fs":
        return FilesystemStore(tmp_path / "artifacts")
    return SwiftStore(MemorySwift(), "test-artifacts")


def put(store, version=V1, body=BODY, iri=IRI, label="作品 % café", partner="partner"):
    return store.put(iri, body, partner=partner, type="Person", label=label, published_at=version)


def test_missing(store):
    assert store.get(IRI) is None
    assert store.get_version(IRI, V1) is None
    assert store.list_versions(IRI) == []
    assert store.list() == []
    store.delete_version(IRI, V1)
    store.delete(IRI)
    assert store.health()["ok"] is True


def test_round_trip_history_and_listing(store):
    assert put(store)
    first = store.get(IRI)
    assert first.iri == IRI
    assert first.body == BODY
    assert first.metadata == {"iri": IRI, "partner": "partner", "type": "Person",
                              "label": "作品 % café", "published_at": V1}
    put(store, V2, b"second")
    assert store.get(IRI).body == b"second"
    assert store.get_version(IRI, V1) == first
    versions = store.list_versions(IRI)
    assert [(v.published_at, v.is_current) for v in versions] == [(V2, True), (V1, False)]
    assert versions[1].label == first.label
    assert [(v.iri, v.partner, v.type, v.label) for v in store.list()] == [
        (IRI, "partner", "Person", first.label)]


@pytest.mark.parametrize("label", [None, "", "東京\n%20"])
def test_optional_labels_and_binary_body(store, label):
    put(store, body=b"\x00\xff\n", label=label)
    assert store.get(IRI).label == label
    assert store.get(IRI).body == b"\x00\xff\n"


def test_idempotency_and_conflict(store):
    locator = put(store)
    assert put(store) == locator
    assert len(store.list_versions(IRI)) == 1
    with pytest.raises(VersionConflictError):
        put(store, body=b"changed")
    with pytest.raises(VersionConflictError):
        put(store, partner="changed")
    assert store.get(IRI).body == BODY


def test_pointer_is_authoritative(store):
    put(store)
    put(store, V2, b"second")
    store.restore_pointer(IRI, V1)
    assert store.get(IRI).body == BODY
    store.restore_pointer(IRI, None)
    assert store.get(IRI) is None
    assert store.list() == []
    assert len(store.list_versions(IRI)) == 2
    assert not any(v.is_current for v in store.list_versions(IRI))
    assert store.get_version(IRI, V2).body == b"second"
    with pytest.raises(ValueError):
        store.restore_pointer(IRI, "2026-09-19T00:00:00.000000Z")
    assert store.get(IRI) is None


def test_current_is_last_put_not_highest_timestamp(store):
    put(store, V2, b"second")
    put(store)
    assert store.get(IRI).published_at == V1
    assert [(v.published_at, v.is_current) for v in store.list_versions(IRI)] == [
        (V2, False), (V1, True)]


def test_deletion_and_isolation(store):
    put(store)
    put(store, iri=IRI + "2")
    with pytest.raises(ValueError):
        store.delete_version(IRI, V1)
    put(store, V2)
    store.delete_version(IRI, V1)
    store.delete_version(IRI, V1)
    assert store.get_version(IRI, V1) is None
    store.delete(IRI)
    store.delete(IRI)
    assert store.get(IRI) is None
    assert store.list_versions(IRI) == []
    assert [v.iri for v in store.list()] == [IRI + "2"]


@pytest.mark.parametrize("iri", [".", "..", "../../outside", "a/b", "a%2Fb", "h_abc", "文" * 500])
def test_safe_identifiers(store, iri):
    key = iri_to_key(iri)
    assert "/" not in key and key not in (".", "..") and len(key) < 200
    put(store, iri=iri)
    assert store.get(iri).iri == iri
    assert store.list()[0].iri == iri
    assert iri_to_key("a/b") != iri_to_key("a%2Fb")


@pytest.mark.parametrize("version", ["", "../bad", "2026-02-30T00:00:00.000000Z", "2026-09-18T00:00:00Z", "2026-09-18T00:00:00.000000+00:00"])
def test_invalid_version(store, version):
    with pytest.raises(ValueError):
        put(store, version)
    assert store.list() == []


@pytest.mark.parametrize("iri", ["", "  "])
def test_blank_identifier(store, iri):
    with pytest.raises(ValueError):
        put(store, iri=iri)


def test_failed_pointer_write_preserves_current(store, monkeypatch):
    put(store)

    def fail(*args, **kwargs):
        raise OSError("Injected pointer failure")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_write_pointer", fail)
        with pytest.raises(OSError):
            put(store, V2, b"second")
    assert store.get(IRI).published_at == V1
    assert store.get_version(IRI, V2).body == b"second"
    put(store, V2, b"second")
    assert store.get(IRI).published_at == V2


def test_filesystem_reopen(tmp_path):
    put(FilesystemStore(tmp_path))
    assert FilesystemStore(tmp_path).get(IRI).body == BODY


@pytest.mark.parametrize("status", [401, 403, 500])
def test_swift_errors_are_not_missing(status):
    connection = MemorySwift()
    store = SwiftStore(connection, "test")
    put(store)
    connection.failure = status
    for operation in [lambda: store.get(IRI), lambda: store.get_version(IRI, V1),
                      lambda: store.list_versions(IRI), store.list,
                      lambda: store.delete(IRI), lambda: put(store, V2)]:
        with pytest.raises(ClientException) as error:
            operation()
        assert error.value.http_status == status
    assert store.health()["ok"] is False
    with pytest.raises(ClientException):
        SwiftStore(connection, "test")