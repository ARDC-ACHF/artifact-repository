"""Shared pydantic data models / API contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationErrorItem(BaseModel):
    """A single structured validation error."""

    path: str
    code: str
    message: str


class ValidationResult(BaseModel):
    """Outcome of validating a Linked Art artifact."""

    valid: bool
    errors: list[ValidationErrorItem] = Field(default_factory=list)


class ArtifactSummary(BaseModel):
    """A lightweight summary of a stored artifact (list/search results)."""

    id: str  # original IRI
    type: str
    partner: str
    label: str | None = None
    locator: str  # /api/v1/artifacts/{url-encoded-iri}


class PublishResponse(BaseModel):
    """Response body returned on a successful publish."""

    id: str
    locator: str
    partner: str
    type: str
    stored_at: str
    published_at: str  # UTC publication date / snapshot id of the stored version
    version_created: bool = True  # False on idempotent (unchanged) re-publish
    snapshot_of: str | None = None  # published_at superseded, or None on first publish


class ArtifactVersion(BaseModel):
    """A single version in an artifact's history."""

    published_at: str  # snapshot date == version id
    is_current: bool
    type: str
    partner: str
    label: str | None = None
    locator: str  # /api/v1/artifacts/{iri}/versions/{published_at}


class VersionListResponse(BaseModel):
    """The full version history of an artifact, newest first."""

    id: str  # original IRI
    total: int
    versions: list[ArtifactVersion] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """Cross-domain search response."""

    query: str
    total: int
    results: list[ArtifactSummary] = Field(default_factory=list)


class ListResponse(BaseModel):
    """Paged list of artifact summaries."""

    total: int
    limit: int
    offset: int
    results: list[ArtifactSummary] = Field(default_factory=list)
