import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import pytest

from app.extract import extract_body_text, extract_label
from app.index import FtsIndex
from app.partners import partner_for_iri
from app.service import RepositoryService, ValidationFailed, locator_for, version_locator_for
from app.storage.fs_store import FilesystemStore
from app.validation.validator import CONTEXT_URL


@pytest.fixture
def resources(tmp_path):
    storage = FilesystemStore(tmp_path / "storage")
    index = FtsIndex(tmp_path / "index.sqlite")
    yield RepositoryService(storage, index), storage, index
    index.close()


@pytest.fixture
def payload():
    return {"@context": CONTEXT_URL, "id": "https://nga.gov.au/object/1?x=a&y=+%/#part", "type": "HumanMadeObject", "_label": "Blue painting"}


def test_locators(payload):
    iri = payload["id"]
    assert urlsplit(locator_for(iri)).path == "/api/v1/artifacts/item"
    assert parse_qs(urlsplit(locator_for(iri)).query) == {"iri": [iri]}
    stamp = "2026-01-01T00:00:00.000000Z"
    locator = urlsplit(version_locator_for(iri, stamp))
    assert locator.path == "/api/v1/artifacts/version"
    assert parse_qs(locator.query) == {"iri": [iri], "published_at": [stamp]}


def test_publication_history_and_retry_repair(resources, payload, monkeypatch):
    service, storage, index = resources
    monkeypatch.setattr("app.service._now_published_at", lambda: "2026-12-31T23:59:59.999999Z")
    first = service.publish(payload)
    assert first.version_created and first.snapshot_of is None
    assert first.stored_at == version_locator_for(payload["id"], first.published_at)
    index.clear()
    retry = service.publish(dict(reversed(list(payload.items()))))
    assert not retry.version_created and retry.published_at == first.published_at
    assert retry.snapshot_of is None and index.count() == 1
    assert service.list_versions(payload["id"]).total == 1
    changed = {**payload, "_label": "Red painting"}
    second = service.publish(changed)
    assert second.published_at == "2027-01-01T00:00:00.000000Z"
    assert second.snapshot_of == first.published_at
    assert second.stored_at == version_locator_for(payload["id"], second.published_at)
    assert json.loads(service.get_raw(payload["id"])) == changed
    assert json.loads(service.get_version_raw(payload["id"], first.published_at)) == payload
    versions = service.list_versions(payload["id"]).versions
    assert [v.is_current for v in versions] == [True, False]
    assert service.search("Blue")[0] == 0
    assert service.search("Red")[0] == 1


@pytest.mark.parametrize("existing", [False, True])
def test_index_failure_rolls_back(resources, payload, monkeypatch, existing):
    service, storage, index = resources
    if existing:
        service.publish(payload)
    before = storage.get(payload["id"])
    versions = storage.list_versions(payload["id"])
    def fail(*args, **kwargs):
        raise RuntimeError("index unavailable")
    monkeypatch.setattr(index, "upsert", fail)
    with pytest.raises(RuntimeError, match="index unavailable"):
        service.publish({**payload, "_label": "Changed"})
    assert storage.get(payload["id"]) == before
    assert storage.list_versions(payload["id"]) == versions
    assert index.count() == int(existing)


def test_real_index_failure_preserves_storage_and_index(resources, payload, monkeypatch):
    service, storage, index = resources
    service.publish(payload)
    before = storage.get(payload["id"])
    versions = storage.list_versions(payload["id"])
    monkeypatch.setattr("app.service.extract_body_text", lambda payload: object())
    with pytest.raises(sqlite3.ProgrammingError):
        service.publish({**payload, "_label": "Changed"})
    assert storage.get(payload["id"]) == before
    assert storage.list_versions(payload["id"]) == versions
    assert service.search("Blue")[0] == 1
    assert service.search("Changed")[0] == 0


def test_rollback_failure_preserves_original_error(resources, payload, monkeypatch, caplog):
    service, storage, index = resources
    def index_failure(*args, **kwargs):
        raise RuntimeError("index unavailable")
    def rollback_failure(*args, **kwargs):
        raise OSError("storage unavailable")
    monkeypatch.setattr(index, "upsert", index_failure)
    monkeypatch.setattr(storage, "restore_pointer", rollback_failure)
    with pytest.raises(RuntimeError, match="index unavailable"):
        service.publish(payload)
    assert "Publication rollback failed" in caplog.text
    assert storage.get(payload["id"]) is not None
    assert len(storage.list_versions(payload["id"])) == 1


def test_reindex_and_queries(resources, payload):
    service, storage, index = resources
    service.publish(payload)
    index.clear()
    assert service.reindex() == 1
    total, records = service.search("paint", types=["HumanMadeObject"], partners=["nga"])
    assert total == 1 and records[0].id == payload["id"]
    assert service.list(partner="nga", type="HumanMadeObject")[0] == 1
    assert service.list(partner="ausstage")[0] == 0
    assert service.get_current("missing") is None
    assert service.get_raw("missing") is None
    assert service.list_versions("missing") is None
    assert service.get_version_raw("missing", "2026-01-01T00:00:00.000000Z") is None
    with pytest.raises(ValidationFailed):
        service.publish({})
    assert index.count() == 1


def test_concurrent_identical_publications(resources, payload):
    service, storage, index = resources
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(service.publish, [payload] * 16))
    assert sum(r.version_created for r in results) == 1
    assert len(storage.list_versions(payload["id"])) == 1
    assert index.count() == 1


def test_extraction_and_partners():
    payload = {"_label": "  ", "identified_by": {"type": "Name", "content": "Title"}, "part": [{"_label": "Title", "value": " Detail "}], "id": "ignored"}
    assert extract_label(payload) == "Title"
    assert extract_body_text(payload) == "Title Detail"
    assert extract_label({"_label": "Primary"}) == "Primary"
    assert extract_label({"identified_by": [None, {"type": "Identifier", "content": "No"}]}) is None
    assert extract_body_text({}) == ""
    assert partner_for_iri("https://user@WWW.AUSSTAGE.ORG.AU:443/event/1") == "ausstage"
    assert partner_for_iri("https://austlit.edu.au/1") == "austlit"
    assert partner_for_iri("https://www.new-partner.example/1") == "new-partner"
    assert partner_for_iri("relative-id") == "unknown"