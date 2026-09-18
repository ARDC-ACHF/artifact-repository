"""Validation and repository API response contracts."""

from pydantic import BaseModel, Field


class ValidationErrorItem(BaseModel):
    path: str
    code: str
    message: str


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationErrorItem] = Field(default_factory=list)


class ArtifactSummary(BaseModel):
    id: str
    type: str
    partner: str
    label: str | None = None
    locator: str


class PublishResponse(BaseModel):
    id: str
    locator: str
    partner: str
    type: str
    stored_at: str
    published_at: str
    version_created: bool = True
    snapshot_of: str | None = None


class DeleteResponse(BaseModel):
    id: str
    deleted: bool = True
    published_at: str | None = None


class ArtifactVersion(BaseModel):
    published_at: str
    is_current: bool
    type: str
    partner: str
    label: str | None = None
    locator: str


class VersionListResponse(BaseModel):
    id: str
    total: int
    versions: list[ArtifactVersion] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[ArtifactSummary] = Field(default_factory=list)


class ListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    results: list[ArtifactSummary] = Field(default_factory=list)
