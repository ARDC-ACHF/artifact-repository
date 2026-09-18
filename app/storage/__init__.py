"""Storage backends with caller-injected configuration and connections."""

from .base import (
    ListEntry, StorageBackend, StoredArtifact, VersionConflictError, VersionEntry,
    iri_to_key, validate_version_id,
)
from .fs_store import FilesystemStore
from .swift_store import SwiftStore

__all__ = [
    "FilesystemStore", "SwiftStore", "StorageBackend", "StoredArtifact",
    "ListEntry", "VersionEntry", "VersionConflictError", "iri_to_key",
    "validate_version_id",
]