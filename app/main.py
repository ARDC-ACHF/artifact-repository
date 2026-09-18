"""FastAPI application entrypoint.

Builds the storage backend and search index at startup (both local-first, so no
environment is required), mounts the API routers and the static demo frontend.

Run locally with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app import __version__
from app.api import read_payload, repository_router
from app.index import FtsIndex
from app.models import ValidationResult
from app.service import RepositoryService, ValidationFailed
from app.storage.fs_store import FilesystemStore
from app.validation.validator import LinkedArtValidator


def create_app(*, service: RepositoryService | None = None, data_dir: Path = Path("data")) -> FastAPI:
    owned_index = None
    initialization_lock = Lock()

    def get_service():
        nonlocal service, owned_index
        with initialization_lock:
            if service is None:
                storage = FilesystemStore(data_dir / "artifacts")
                owned_index = FtsIndex(data_dir / "index.sqlite3")
                service = RepositoryService(storage, owned_index)
            return service

    @asynccontextmanager
    async def lifespan(app):
        nonlocal service, owned_index
        try:
            yield
        finally:
            if owned_index is not None:
                owned_index.close()
                owned_index = None
                service = None

    app = FastAPI(
        lifespan=lifespan,
        title="Linked Art Interoperability Repository",
        version=__version__,
        description=(
            "API foundation for a Linked Art interoperability repository. "
            "Offline validation, versioned publication, retrieval and full-text search."
        ),
    )
    validator = LinkedArtValidator()
    app.include_router(repository_router(get_service))

    @app.exception_handler(ValidationFailed)
    async def validation_failed(request, exc):
        return JSONResponse(status_code=422, content=exc.result.model_dump())

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
        payload = await read_payload(request)
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

