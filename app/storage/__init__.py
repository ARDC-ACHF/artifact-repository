"""Storage backends for the artifact repository."""

from __future__ import annotations

from app.config import Settings
from app.storage.base import StorageBackend, StoredArtifact, VersionEntry


def build_storage(settings: Settings) -> StorageBackend:
    """Instantiate the storage backend selected by ``settings.storage_backend``."""
    if settings.storage_backend == "swift":
        from app.storage.swift_store import SwiftStore

        return SwiftStore(settings)

    from app.storage.fs_store import FilesystemStore

    return FilesystemStore(settings)


__all__ = ["StorageBackend", "StoredArtifact", "VersionEntry", "build_storage"]
