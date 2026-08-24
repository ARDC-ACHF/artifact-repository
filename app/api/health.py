"""Liveness/readiness endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_index, get_storage
from app.index import FtsIndex
from app.storage import StorageBackend

router = APIRouter(tags=["health"])


@router.get("/health")
def health(
    storage: StorageBackend = Depends(get_storage),
    index: FtsIndex = Depends(get_index),
) -> dict[str, object]:
    """Report storage + index connectivity status.

    Returns ``status: ok`` only when both the storage backend and the index are
    healthy; otherwise ``status: degraded`` (the endpoint itself always 200s so
    orchestrators can read the detail).
    """
    storage_health = storage.health()
    index_health = index.health()
    ok = bool(storage_health.get("ok")) and bool(index_health.get("ok"))
    return {
        "status": "ok" if ok else "degraded",
        "storage": storage_health,
        "index": index_health,
    }
