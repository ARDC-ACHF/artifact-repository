"""FastAPI application entrypoint.

Builds the storage backend and search index at startup (both local-first, so no
environment is required), mounts the API routers and the static demo frontend.

Run locally with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import get_settings
from app.index import FtsIndex
from app.service import RepositoryService
from app.storage import build_storage

_WEB_DIR = Path(__file__).resolve().parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.ensure_local_dirs()

    app.state.settings = settings
    app.state.storage = build_storage(settings)
    app.state.index = FtsIndex(settings.index_path)
    app.state.service = RepositoryService(
        settings, app.state.storage, app.state.index
    )
    try:
        yield
    finally:
        app.state.index.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Linked Art Interoperability Repository",
        version=__version__,
        description=(
            "A prototype repository that ingests, validates and stores Linked Art "
            "JSON-LD artifacts from partner platforms and offers cross-domain search."
        ),
        lifespan=lifespan,
    )

    # Routers are imported lazily to keep import-time side effects minimal.
    from app.api import artifacts, health, search

    app.include_router(health.router)
    app.include_router(artifacts.router)
    app.include_router(search.router)

    # Serve the demo frontend at the root if present.
    if _WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")

    return app


app = create_app()
