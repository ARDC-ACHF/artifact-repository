"""Cross-domain search endpoint (base path ``/api/v1``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.deps import get_service
from app.models import SearchResponse
from app.service import RepositoryService

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., description="Free-text query (required)."),
    type: list[str] | None = Query(default=None, description="Filter by type (repeatable)."),
    partner: list[str] | None = Query(
        default=None, description="Filter by partner (repeatable)."
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: RepositoryService = Depends(get_service),
) -> SearchResponse:
    """Search across all partner domains with optional type/partner filters."""
    total, results = service.search(
        q, types=type, partners=partner, limit=limit, offset=offset
    )
    return SearchResponse(query=q, total=total, results=results)
