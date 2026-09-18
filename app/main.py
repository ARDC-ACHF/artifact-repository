"""FastAPI application entrypoint.

Run locally with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

import json

from fastapi import FastAPI, Request, Response

from app import __version__
from app.models import ValidationErrorItem, ValidationResult
from app.validation.validator import LinkedArtValidator


def create_app() -> FastAPI:
    app = FastAPI(
        title="Linked Art Interoperability Repository",
        version=__version__,
        description=(
            "API foundation for a Linked Art interoperability repository. "
            "Basic offline validation is available; publication and search are not implemented yet."
        ),
    )
    validator = LinkedArtValidator()

    @app.post(
        "/api/v1/artifacts/validate",
        response_model=ValidationResult,
        responses={422: {"model": ValidationResult}},
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {}}},
            }
        },
    )
    async def validate_artifact(request: Request, response: Response) -> ValidationResult:
        """Check a JSON document without storing it."""
        def reject_constant(value: str) -> None:
            raise ValueError("Non-JSON numeric constant")

        try:
            payload = json.loads(await request.body(), parse_constant=reject_constant)
        except ValueError:
            result = ValidationResult(
                valid=False,
                errors=[ValidationErrorItem(
                    path="$",
                    code="invalid_json",
                    message="Request body must be valid JSON.",
                )],
            )
        else:
            result = validator.validate(payload)
        if not result.valid:
            response.status_code = 422
        return result

    @app.get("/health")
    def health() -> dict[str, str]:
        """Report application liveness, not storage or index readiness."""
        return {"status": "ok"}

    return app


app = create_app()