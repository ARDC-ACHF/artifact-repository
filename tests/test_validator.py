"""Unit tests for the pragmatic Linked Art validator."""

from __future__ import annotations

import pytest

CONTEXT = "https://linked.art/ns/v1/linked-art.json"


@pytest.mark.parametrize(
    "stem",
    [
        "ausstage_event_12345",  # Activity (performance)
        "austlit_work_5551",  # LinguisticObject (literature)
        "nga_object_98765",  # HumanMadeObject (art)
        "ausstage_person_637820",  # Person (shared entity)
    ],
)
def test_valid_artifacts_per_domain(validator, sample_artifacts, stem):
    result = validator.validate(sample_artifacts[stem])
    assert result.valid, result.errors
    assert result.errors == []


def test_missing_id_reports_missing_field(validator):
    payload = {"@context": CONTEXT, "type": "Activity"}
    result = validator.validate(payload)
    assert not result.valid
    codes = {(e.code, e.path) for e in result.errors}
    assert ("missing_field", "$.id") in codes


def test_missing_context_and_type(validator):
    result = validator.validate({"id": "https://example.org/x"})
    assert not result.valid
    codes = {e.code for e in result.errors}
    assert "missing_field" in codes


def test_unsupported_type(validator):
    payload = {"@context": CONTEXT, "id": "https://example.org/x", "type": "Painting"}
    result = validator.validate(payload)
    assert not result.valid
    errs = [e for e in result.errors if e.code == "unsupported_type"]
    assert errs and errs[0].path == "$.type"


def test_non_object_payload(validator):
    result = validator.validate([1, 2, 3])
    assert not result.valid
    assert result.errors[0].code == "invalid_type"


def test_malformed_jsonld_context(validator):
    # @context of the wrong JSON-LD type must fail expansion.
    payload = {"@context": 123, "id": "https://example.org/x", "type": "Activity"}
    result = validator.validate(payload)
    assert not result.valid
    assert any(e.code == "invalid_jsonld" for e in result.errors)


def test_remote_context_blocked_offline(validator):
    # A non-bundled remote context must not be fetched over the network.
    payload = {
        "@context": "https://example.org/some-other-context.json",
        "id": "https://example.org/x",
        "type": "Activity",
    }
    result = validator.validate(payload)
    assert not result.valid
    assert any(e.code == "invalid_jsonld" for e in result.errors)
