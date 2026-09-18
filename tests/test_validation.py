"""Contract tests for the offline validation slice."""

import json
from pathlib import Path
import socket

import pytest
from fastapi.testclient import TestClient
from pyld import jsonld

from app.main import create_app
from app.validation.context_loader import build_document_loader
from app.validation.supported_types import SUPPORTED_TYPES
from app.validation.validator import CONTEXT_PATH, CONTEXT_URL, LinkedArtValidator


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def blocked(*args, **kwargs):
        pytest.fail("Validation attempted network access")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.chdir(tmp_path)
    yield
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def payload():
    return {"@context": CONTEXT_URL, "id": "https://example.org/object/1", "type": "HumanMadeObject"}


@pytest.fixture
def validator():
    return LinkedArtValidator()


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


@pytest.mark.parametrize("type_value", sorted(SUPPORTED_TYPES))
def test_supported_types(payload, validator, client, type_value):
    payload["type"] = type_value
    assert validator.validate(payload).model_dump() == {"valid": True, "errors": []}
    response = client.post("/api/v1/artifacts/validate", json=payload)
    assert response.status_code == 200
    assert response.json() == {"valid": True, "errors": []}


@pytest.mark.parametrize("filename", ["ausstage_event_12345.json", "austlit_work_5551.json", "nga_object_98765.json"])
def test_representative_documents(validator, client, filename):
    payload = json.loads((Path(__file__).parent / "fixtures" / filename).read_text())
    assert validator.validate(payload).valid
    assert client.post("/api/v1/artifacts/validate", json=payload).status_code == 200


@pytest.mark.parametrize("field", ["@context", "id", "type"])
@pytest.mark.parametrize("value,code", [(None, "missing_field"), ("", "missing_field"), ("  ", "missing_field"), ([], "missing_field"), ({}, "invalid_type"), (7, "invalid_type"), (False, "invalid_type"), (["Person"], "invalid_type")])
def test_field_errors(payload, validator, client, field, value, code):
    payload[field] = value
    result = validator.validate(payload)
    assert not result.valid
    assert [(e.path, e.code) for e in result.errors] == [(f"$.{field}", code)]
    response = client.post("/api/v1/artifacts/validate", json=payload)
    assert response.status_code == 422
    assert response.json() == result.model_dump()


def test_missing_fields(validator):
    result = validator.validate({})
    assert [(e.path, e.code) for e in result.errors] == [
        ("$.@context", "missing_field"), ("$.id", "missing_field"), ("$.type", "missing_field")
    ]


@pytest.mark.parametrize("context", [{"id": "@type"}, [CONTEXT_URL]])
def test_inline_and_array_contexts(payload, validator, client, context):
    payload["@context"] = context
    result = validator.validate(payload)
    assert [(e.path, e.code) for e in result.errors] == [("$.@context", "invalid_type")]
    response = client.post("/api/v1/artifacts/validate", json=payload)
    assert response.status_code == 422
    assert response.json() == result.model_dump()


@pytest.mark.parametrize("payload", [None, [], "text", 1, False])
def test_non_objects(validator, client, payload):
    result = validator.validate(payload)
    assert [(e.path, e.code) for e in result.errors] == [("$", "invalid_type")]
    response = client.post("/api/v1/artifacts/validate", content=json.dumps(payload))
    assert response.status_code == 422
    assert response.json() == result.model_dump()


@pytest.mark.parametrize("body", [b"", b"{", b"\xff", b"NaN", b"Infinity", b'{"id": NaN}'])
def test_malformed_json(client, body):
    response = client.post("/api/v1/artifacts/validate", content=body)
    assert response.status_code == 422
    assert response.json() == {"valid": False, "errors": [{
        "path": "$", "code": "invalid_json", "message": "Request body must be valid JSON."
    }]}


@pytest.mark.parametrize("context", ["https://example.org/context", CONTEXT_URL + "#fragment"])
def test_remote_contexts(payload, validator, context):
    payload["@context"] = context
    assert [(e.path, e.code) for e in validator.validate(payload).errors] == [("$.@context", "unsupported_context")]


@pytest.mark.parametrize("context", [{"id": "@type"}, [CONTEXT_URL], None, "https://example.org/context"])
def test_nested_contexts(payload, validator, context):
    payload["part"] = [{"@context": context, "id": "https://example.org/part/1"}]
    assert [(e.path, e.code) for e in validator.validate(payload).errors] == [("$.part[0].@context", "unsupported_context")]


def test_unsupported_type(payload, validator):
    payload["type"] = "NotAClass"
    assert [(e.path, e.code) for e in validator.validate(payload).errors] == [("$.type", "unsupported_type")]


def test_expansion_error(payload, validator, client):
    payload["identified_by"] = [{"@value": "name", "@type": {}}]
    result = validator.validate(payload)
    assert result.model_dump() == {"valid": False, "errors": [{
        "path": "$", "code": "invalid_jsonld", "message": "JSON-LD expansion failed."
    }]}
    response = client.post("/api/v1/artifacts/validate", json=payload)
    assert response.status_code == 422
    assert response.json() == result.model_dump()


def test_relative_identifiers_are_not_rejected(payload, validator):
    payload["id"] = "relative-id"
    assert validator.validate(payload).valid


def test_loader_blocks_unapproved_urls():
    loader = build_document_loader(CONTEXT_URL, CONTEXT_PATH)
    assert "@context" in loader(CONTEXT_URL)["document"]
    with pytest.raises(jsonld.JsonLdError):
        loader("https://example.org/context")


def test_openapi_contract(client):
    operation = client.get("/openapi.json").json()["paths"]["/api/v1/artifacts/validate"]["post"]
    assert "application/json" in operation["requestBody"]["content"]
    for status in ("200", "422"):
        assert operation["responses"][status]["content"]["application/json"]["schema"]["$ref"].endswith("/ValidationResult")