"""Validation response contracts."""

from pydantic import BaseModel, Field


class ValidationErrorItem(BaseModel):
    path: str
    code: str
    message: str


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationErrorItem] = Field(default_factory=list)