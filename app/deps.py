"""FastAPI dependency accessors for shared singletons.

The storage backend and search index are created once during application
startup (see :mod:`app.main`) and stored on ``app.state``. These helpers expose
them to routers via ``Depends`` / ``request.app.state``.
"""

from __future__ import annotations

from fastapi import Request

from app.config import Settings
from app.index import FtsIndex
from app.storage import StorageBackend


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_storage(request: Request) -> StorageBackend:
    return request.app.state.storage


def get_index(request: Request) -> FtsIndex:
    return request.app.state.index


def get_service(request: Request):
    """Return the shared :class:`app.service.RepositoryService`."""
    return request.app.state.service
