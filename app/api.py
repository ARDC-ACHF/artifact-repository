"""Repository endpoints; identifiers are query parameters, not decoded paths."""

import json

from fastapi import APIRouter, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.models import DeleteResponse, ListResponse, PublishResponse, SearchResponse, ValidationResult, VersionListResponse
from app.service import ValidationFailed
from app.storage.base import validate_version_id


async def read_payload(request: Request):
    def reject_constant(value):
        raise ValueError("Non-JSON numeric constant")

    try:
        return json.loads(await request.body(), parse_constant=reject_constant)
    except ValueError:
        raise ValidationFailed(ValidationResult(valid=False, errors=[{
            "path": "$", "code": "invalid_json", "message": "Request body must be valid JSON."
        }]))


def repository_router(get_service) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post(
        "/artifacts", response_model=PublishResponse, status_code=201,
        responses={200: {"model": PublishResponse}, 422: {"model": ValidationResult}},
        openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": {}}}}},
    )
    async def publish(request: Request, response: Response):
        payload = await read_payload(request)

        def execute():
            return get_service().publish(payload)

        result = await run_in_threadpool(execute)
        response.status_code = 201 if result.version_created else 200
        response.headers["Location"] = result.locator
        return result

    @router.get("/artifacts", response_model=ListResponse)
    def list_artifacts(
        partner: str | None = None, type: str | None = None,
        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    ):
        total, results = get_service().list(partner=partner, type=type, limit=limit, offset=offset)
        return ListResponse(total=total, results=results, limit=limit, offset=offset)

    @router.get("/artifacts/item", response_class=Response,
                responses={200: {"content": {"application/ld+json": {}}}})
    def get_artifact(iri: str = Query(..., min_length=1, pattern=r"\S")):
        body = get_service().get_raw(iri)
        if body is None:
            raise HTTPException(404, "Artifact not found")
        return Response(body, media_type="application/ld+json")

    @router.get("/artifacts/version", response_class=Response,
                responses={200: {"content": {"application/ld+json": {}}}})
    def get_version(iri: str = Query(..., min_length=1, pattern=r"\S"), published_at: str = Query(...)):
        try:
            validate_version_id(published_at)
        except ValueError:
            raise HTTPException(422, "published_at must be a canonical UTC timestamp")
        body = get_service().get_version_raw(iri, published_at)
        if body is None:
            raise HTTPException(404, "Version not found")
        return Response(body, media_type="application/ld+json")

    @router.delete("/artifacts/item", response_model=DeleteResponse, response_model_exclude_none=True,
                   responses={404: {"description": "Artifact not found"}})
    def delete_artifact(iri: str = Query(..., min_length=1, pattern=r"\S")):
        """Permanently delete the artifact and all its snapshots."""
        if not get_service().delete(iri):
            raise HTTPException(404, "Artifact not found")
        return DeleteResponse(id=iri)

    @router.delete("/artifacts/version", response_model=DeleteResponse,
                   responses={404: {"description": "Version not found"}})
    def delete_version(iri: str = Query(..., min_length=1, pattern=r"\S"), published_at: str = Query(...)):
        """Delete a snapshot; if current, promote the newest remaining snapshot.

        Deleting the last snapshot removes the artifact from listing and search.
        """
        try:
            validate_version_id(published_at)
        except ValueError:
            raise HTTPException(422, "published_at must be a canonical UTC timestamp")
        if not get_service().delete_version(iri, published_at):
            raise HTTPException(404, "Version not found")
        return DeleteResponse(id=iri, published_at=published_at)

    @router.get("/artifacts/versions", response_model=VersionListResponse)
    def history(iri: str = Query(..., min_length=1, pattern=r"\S")):
        result = get_service().list_versions(iri)
        if result is None:
            raise HTTPException(404, "Artifact not found")
        return result

    @router.get("/search", response_model=SearchResponse)
    def search(
        q: str = Query(..., min_length=1),
        types: list[str] | None = Query(None), partners: list[str] | None = Query(None),
        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    ):
        total, results = get_service().search(q, types=types, partners=partners, limit=limit, offset=offset)
        return SearchResponse(query=q, total=total, results=results)

    return router