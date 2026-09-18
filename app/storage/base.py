"""Storage models and interface for immutable artifact snapshots.

Backends assume a single writer per artifact. Snapshot and pointer updates are
not distributed transactions: failed publication may leave staged snapshots,
but does not deliberately remove the previous current pointer.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


class VersionConflictError(ValueError):
    """A timestamp already belongs to a different body or metadata."""


def iri_to_key(iri: str) -> str:
    """Validate an IRI and map it into a uniform, path-safe hash namespace."""
    if not isinstance(iri, str) or not iri.strip():
        raise ValueError("iri must be a nonblank string")
    return "h_" + hashlib.sha256(iri.encode("utf-8")).hexdigest()


def validate_version_id(published_at: str) -> str:
    """Require a real UTC date in canonical YYYY-MM-DDTHH:MM:SS.ffffffZ form."""
    if not isinstance(published_at, str) or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z",
        published_at,
    ) is None:
        raise ValueError("published_at must be a canonical UTC timestamp")
    datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%S.%fZ")
    return published_at


@dataclass
class StoredArtifact:
    """Raw artifact bytes and preserved metadata."""

    iri: str
    body: bytes
    partner: str = ""
    type: str = ""
    label: str | None = None
    published_at: str | None = None

    @property
    def metadata(self) -> dict[str, str]:
        meta = {"iri": self.iri, "partner": self.partner, "type": self.type}
        if self.label is not None:
            meta["label"] = self.label
        if self.published_at is not None:
            meta["published_at"] = self.published_at
        return meta


@dataclass
class ListEntry:
    """Metadata for a current artifact."""

    iri: str
    partner: str = ""
    type: str = ""
    label: str | None = None


@dataclass
class VersionEntry:
    """Metadata for a snapshot in newest-first history."""

    iri: str
    published_at: str
    is_current: bool
    partner: str = ""
    type: str = ""
    label: str | None = None


class StorageBackend(ABC):
    """Single-writer storage without cross-object or distributed transactions."""

    @abstractmethod
    def put(
        self, iri: str, body: bytes, *, partner: str, type: str,
        label: str | None = None, published_at: str,
    ) -> str:
        """Store a snapshot, then point to it and return its locator.

        Identical retries are idempotent; differing bytes or metadata at the
        same timestamp raise VersionConflictError. Current means last successful
        put, not greatest timestamp. Failed pointer writes can leave snapshots.
        """

    @abstractmethod
    def get(self, iri: str) -> StoredArtifact | None:
        """Return the explicitly pointed-to snapshot, or None."""

    @abstractmethod
    def get_version(self, iri: str, published_at: str) -> StoredArtifact | None:
        """Return the specified snapshot, or None."""

    @abstractmethod
    def list_versions(self, iri: str) -> list[VersionEntry]:
        """List snapshots newest first, including snapshots without a pointer."""

    @abstractmethod
    def restore_pointer(self, iri: str, published_at: str | None) -> None:
        """Point to an existing snapshot, or remove the pointer for None.

        A missing target raises ValueError without changing the pointer.
        """

    @abstractmethod
    def delete_version(self, iri: str, published_at: str) -> None:
        """Delete a snapshot, no-op if absent; reject current with ValueError."""

    @abstractmethod
    def delete(self, iri: str) -> None:
        """Remove the pointer before deleting all snapshots."""

    @abstractmethod
    def list(self) -> list[ListEntry]:
        """Enumerate only artifacts with a current pointer and snapshot."""

    @abstractmethod
    def health(self) -> dict[str, object]:
        """Return backend status; connection and authentication errors propagate."""

