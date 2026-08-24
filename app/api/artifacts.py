"""Artifact ingestion + retrieval endpoints (base path ``/api/v1``)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from app.deps import get_service
from app.models import (
    ListResponse,
    PublishResponse,
    ValidationResult,
    VersionListResponse,
)
from app.service import RepositoryService, ValidationFailed

router = APIRouter(prefix="/api/v1", tags=["artifacts"])


async def _read_json(request: Request) -> tuple[object | None, ValidationResult | None]:
    """Parse the request body as JSON.

    Returns ``(payload, None)`` on success or ``(None, result)`` with a
    structured parse error matching the validation error shape.
    """
    raw = await request.body()
    try:
        return json.loads(raw), None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        result = ValidationResult(
            valid=False,
            errors=[
                {
                    "path": "$",
                    "code": "invalid_json",
                    "message": f"Request body is not valid JSON: {exc}",
                }
            ],
        )
        return None, result


@router.post(
    "/artifacts",
    response_model=PublishResponse,
    status_code=201,
    responses={422: {"description": "Validation failed"}},
)
async def publish_artifact(
    request: Request,
    service: RepositoryService = Depends(get_service),
):
    """Validate and store a single Linked Art artifact synchronously."""
    payload, parse_error = await _read_json(request)
    if parse_error is not None:
        return JSONResponse(status_code=422, content=parse_error.model_dump())
    try:
        response = service.publish(payload)
    except ValidationFailed as exc:
        return JSONResponse(status_code=422, content=exc.result.model_dump())
    return JSONResponse(status_code=201, content=response.model_dump())


@router.post(
    "/artifacts/validate",
    response_model=ValidationResult,
    responses={422: {"description": "Validation failed"}},
)
async def validate_artifact(
    request: Request,
    service: RepositoryService = Depends(get_service),
):
    """Dry-run validation: validates only, never stores."""
    payload, parse_error = await _read_json(request)
    if parse_error is not None:
        return JSONResponse(status_code=422, content=parse_error.model_dump())
    result = service.validate(payload)
    status = 200 if result.valid else 422
    return JSONResponse(status_code=status, content=result.model_dump())


@router.get("/artifacts", response_model=ListResponse)
def list_artifacts(
    partner: str | None = Query(default=None),
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: RepositoryService = Depends(get_service),
) -> ListResponse:
    """List artifact summaries with optional partner/type filters and paging."""
    total, results = service.list(
        partner=partner, type=type, limit=limit, offset=offset
    )
    return ListResponse(total=total, limit=limit, offset=offset, results=results)


@router.get("/artifacts/{iri:path}/versions", response_model=VersionListResponse)
def list_artifact_versions(
    iri: str,
    service: RepositoryService = Depends(get_service),
):
    """List all versions of an IRI, newest first, with the current one flagged.

    Returns ``404`` if the IRI is unknown. Historical snapshots remain listed
    indefinitely.
    """
    history = service.list_versions(iri)
    if history is None:
        return JSONResponse(status_code=404, content={"detail": "Not found", "id": iri})
    return history


@router.get(
    "/artifacts/{iri:path}/versions/{published_at}",
    responses={
        200: {"content": {"application/ld+json": {}}},
        404: {"description": "Version not found"},
    },
)
def get_artifact_version(
    iri: str,
    published_at: str,
    service: RepositoryService = Depends(get_service),
):
    """Retrieve a specific version's JSON-LD verbatim (current or snapshot).

    ``{published_at}`` is the URL-encoded publication date from the versions
    list. Returns ``404`` if the IRI or that version is unknown.
    """
    body = service.get_version_raw(iri, published_at)
    if body is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "Not found", "id": iri, "published_at": published_at},
        )
    return Response(
        content=body,
        media_type="application/ld+json",
        headers={"X-Published-At": published_at},
    )


@router.get(
    "/artifacts/{iri:path}",
    responses={
        200: {"content": {"application/ld+json": {}}},
        404: {"description": "Artifact not found"},
    },
)
def get_artifact(
    iri: str,
    service: RepositoryService = Depends(get_service),
):
    """Retrieve the stored JSON-LD for an IRI's current version, verbatim.

    ``{iri}`` is the URL-encoded original IRI; Starlette decodes it back to the
    raw IRI before it reaches this handler. The response carries the current
    version's publication date in the ``X-Published-At`` header.
    """
    stored = service.get_current(iri)
    if stored is None:
        return JSONResponse(status_code=404, content={"detail": "Not found", "id": iri})
    headers = {}
    if stored.published_at:
        headers["X-Published-At"] = stored.published_at
    return Response(
        content=stored.body,
        media_type="application/ld+json",
        headers=headers,
    )
