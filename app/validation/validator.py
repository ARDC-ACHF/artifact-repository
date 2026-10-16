"""Basic profile checks, not full Linked Art or CIDOC-CRM conformance."""

from pathlib import Path
from typing import Any

from pyld import jsonld

from app.models import ValidationErrorItem, ValidationResult
from app.validation.context_loader import build_document_loader
from app.validation.supported_types import is_supported

CONTEXT_URL = "https://linked.art/ns/v1/linked-art.json"
CONTEXT_PATH = Path(__file__).parent / "context" / "linked-art.json"


class LinkedArtValidator:
    def __init__(self) -> None:
        self._loader = build_document_loader(CONTEXT_URL, CONTEXT_PATH)

    def validate(self, payload: Any) -> ValidationResult:
        errors: list[ValidationErrorItem] = []

        def error(path: str, code: str, message: str) -> None:
            errors.append(ValidationErrorItem(path=path, code=code, message=message))

        if not isinstance(payload, dict):
            error("$", "invalid_type", "Artifact must be a JSON object.")
            return ValidationResult(valid=False, errors=errors)

        for field in ("@context", "id", "type"):
            value = payload.get(field)
            if (
                value is None
                or value == []
                or (isinstance(value, str) and not value.strip())
            ):
                error(
                    f"$.{field}", "missing_field",
                    f"Required field '{field}' is missing or empty.",
                )
            elif not isinstance(value, str):
                error(f"$.{field}", "invalid_type", f"Top-level '{field}' must be a string.")
            elif field == "type" and not is_supported(value):
                error(
                    "$.type", "unsupported_type",
                    "Top-level 'type' is not a supported Linked Art class.",
                )

        def check_contexts(value: Any, path: str = "$") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    child_path = f"{path}.{key}"
                    if key == "@context":
                        if child != CONTEXT_URL and not any(
                            e.path == child_path for e in errors
                        ):
                            error(
                                child_path, "unsupported_context",
                                "Only the bundled Linked Art context URL is accepted.",
                            )
                    else:
                        check_contexts(child, child_path)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    check_contexts(child, f"{path}[{index}]")

        check_contexts(payload)
        if not errors:
            try:
                expanded = jsonld.expand(payload, options={"documentLoader": self._loader})
            except jsonld.JsonLdError:
                error("$", "invalid_jsonld", "JSON-LD expansion failed.")
            else:
                if not expanded:
                    error("$", "invalid_jsonld", "JSON-LD expansion produced an empty document.")

        return ValidationResult(valid=not errors, errors=errors)