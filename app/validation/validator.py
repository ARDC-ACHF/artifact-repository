"""Pragmatic Linked Art validator.

This is intentionally a *profile* check, not full CIDOC-CRM / SHACL
conformance. It verifies that a payload:

1. is a JSON object;
2. has the required top-level fields ``@context``, ``id``, ``type``;
3. carries a ``type`` within the supported pragmatic profile
   (see :mod:`app.validation.supported_types`);
4. expands cleanly as JSON-LD against the bundled Linked Art context.

Errors are collected (not raised) and returned as a :class:`ValidationResult`
so partners get a complete list of problems in one round-trip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pyld import jsonld

from app.models import ValidationErrorItem, ValidationResult
from app.validation.context_loader import build_document_loader
from app.validation.supported_types import is_supported

_REQUIRED_FIELDS = ("@context", "id", "type")


class LinkedArtValidator:
    """Validates artifacts against the pragmatic Linked Art profile."""

    def __init__(self, context_url: str, context_path: Path | str) -> None:
        self._loader = build_document_loader(context_url, Path(context_path))

    def validate(self, payload: Any) -> ValidationResult:
        """Validate a decoded JSON payload, returning a structured result."""
        errors: list[ValidationErrorItem] = []

        if not isinstance(payload, dict):
            errors.append(
                ValidationErrorItem(
                    path="$",
                    code="invalid_type",
                    message="Artifact must be a JSON object.",
                )
            )
            return ValidationResult(valid=False, errors=errors)

        self._check_required_fields(payload, errors)
        self._check_supported_type(payload, errors)
        # Only attempt JSON-LD expansion when the structural essentials
        # (@context + at least one of id/type) are present; otherwise the
        # expansion error would be redundant with the missing_field errors.
        if "@context" in payload:
            self._check_jsonld_expands(payload, errors)

        return ValidationResult(valid=not errors, errors=errors)

    # --- individual checks ----------------------------------------------
    @staticmethod
    def _check_required_fields(
        payload: dict, errors: list[ValidationErrorItem]
    ) -> None:
        for field in _REQUIRED_FIELDS:
            if field not in payload or payload[field] in (None, "", []):
                errors.append(
                    ValidationErrorItem(
                        path="$" if field == "@context" else f"$.{field}",
                        code="missing_field",
                        message=f"Required field '{field}' is missing.",
                    )
                )

    @staticmethod
    def _check_supported_type(
        payload: dict, errors: list[ValidationErrorItem]
    ) -> None:
        if "type" not in payload:
            return
        type_value = payload["type"]
        if not isinstance(type_value, str):
            errors.append(
                ValidationErrorItem(
                    path="$.type",
                    code="invalid_type",
                    message="Top-level 'type' must be a string.",
                )
            )
            return
        if not is_supported(type_value):
            errors.append(
                ValidationErrorItem(
                    path="$.type",
                    code="unsupported_type",
                    message=(
                        f"Type '{type_value}' is not a supported Linked Art class."
                    ),
                )
            )

    def _check_jsonld_expands(
        self, payload: dict, errors: list[ValidationErrorItem]
    ) -> None:
        try:
            expanded = jsonld.expand(
                payload, options={"documentLoader": self._loader}
            )
        except jsonld.JsonLdError as exc:
            errors.append(
                ValidationErrorItem(
                    path="$",
                    code="invalid_jsonld",
                    message=f"JSON-LD expansion failed: {exc}",
                )
            )
            return
        if not expanded:
            errors.append(
                ValidationErrorItem(
                    path="$",
                    code="invalid_jsonld",
                    message="JSON-LD expansion produced an empty document.",
                )
            )
