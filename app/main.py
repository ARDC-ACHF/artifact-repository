"""FastAPI application entrypoint.

Run locally with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from starlette.routing import Match

from app import __version__
from app.api import read_payload, repository_router
from app.auth import (
    PUBLIC_READ_PATHS, AuthenticationProvider, install_authentication, providers_from_environment,
    public_read_from_environment,
)
from app.index import FtsIndex
from app.models import ValidationResult
from app.service import RepositoryService, ValidationFailed
from app.storage.fs_store import FilesystemStore
from app.validation.validator import LinkedArtValidator

DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
# Paths owned by the API/docs; the SPA fallback never answers for these.
_RESERVED_PREFIXES = ("api", "docs", "redoc", "openapi.json", "health")


# Read-only GET routes that also answer HEAD (headers only, no body).
HEAD_AS_GET_PATHS = PUBLIC_READ_PATHS | {"/health"}


def _is_reserved(path: str) -> bool:
    first = path.split("/", 1)[0]
    return first in _RESERVED_PREFIXES


class HeadAsGetMiddleware:
    """Answer HEAD on selected GET routes by running the GET handler and dropping the body."""

    def __init__(self, app, paths=HEAD_AS_GET_PATHS):
        self.app = app
        self.paths = frozenset(paths)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "HEAD":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        root_path = scope.get("root_path", "").rstrip("/")
        if root_path and path.startswith(root_path + "/"):
            path = path[len(root_path):]
        if path not in self.paths:
            await self.app(scope, receive, send)
            return

        async def send_without_body(message):
            if message["type"] == "http.response.body":
                if message.get("more_body", False):
                    return
                message = {"type": "http.response.body", "body": b"", "more_body": False}
            await send(message)

        await self.app(dict(scope, method="GET"), receive, send_without_body)


def install_frontend(app: FastAPI, frontend_dir: Path):
    """Serve a built single-page app; unknown non-API paths fall back to index.html.

    Returns the catch-all route so callers can keep it last in the routing table.
    """
    root = frontend_dir.resolve()
    index = root / "index.html"

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def frontend(full_path: str, request: Request):
        if _is_reserved(full_path):
            allowed = set()
            for route in request.app.router.routes:
                if route is not frontend_route and route.matches(request.scope)[0] == Match.PARTIAL:
                    allowed |= getattr(route, "methods", None) or set()
            if allowed:
                return JSONResponse({"detail": "Method Not Allowed"}, status_code=405,
                                    headers={"Allow": ", ".join(sorted(allowed))})
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if full_path and "\x00" not in full_path:
            try:
                candidate = (root / full_path).resolve()
                if candidate.is_relative_to(root) and candidate.is_file():
                    return FileResponse(candidate)
            except (OSError, ValueError):
                pass
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    frontend_route = app.router.routes[-1]
    return frontend_route


def create_app(
    *, service: RepositoryService | None = None, data_dir: Path = Path("data"),
    auth_providers: tuple[AuthenticationProvider, ...] | None = None,
    public_read: bool | None = None, frontend_dir: Path | None = None,
) -> FastAPI:
    owned_index = None
    frontend_route = None
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
        # Keep the SPA catch-all behind any routes registered after create_app().
        if frontend_route is not None and frontend_route in app.router.routes:
            app.router.routes.remove(frontend_route)
            app.router.routes.append(frontend_route)
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

    if frontend_dir is not None and (Path(frontend_dir) / "index.html").is_file():
        frontend_route = install_frontend(app, Path(frontend_dir))

    app.add_middleware(HeadAsGetMiddleware)
    install_authentication(
        app, providers_from_environment() if auth_providers is None else tuple(auth_providers),
        public_read=public_read_from_environment() if public_read is None else public_read,
    )
    return app


app = create_app(
    data_dir=Path(os.environ.get("REPOSITORY_DATA_DIR", "data")),
    frontend_dir=Path(os.environ.get("REPOSITORY_FRONTEND_DIR", DEFAULT_FRONTEND_DIR)),
)