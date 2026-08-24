"""Storage backend interface and shared helpers.

Artifacts are addressed by the partner's own ``id`` IRI. The IRI is encoded to
a storage-safe object key with :func:`iri_to_key`; the raw IRI is always
preserved verbatim in object metadata so externally-resolvable IRIs remain the
lookup handle.
"""

from __future__ import annotations

import hashlib
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass

# Swift object names must stay well under filesystem/URL limits. If a
# URL-encoded IRI exceeds this, we hash it to a fixed-length key while keeping
# the raw IRI in metadata/index for lookup.
_MAX_KEY_LEN = 200


def iri_to_key(iri: str) -> str:
    """Encode an IRI to a storage-safe object key.

    Short IRIs are percent-encoded (reversible, human-browsable). Very long
    IRIs collapse to a stable ``h_<sha256>`` key; the raw IRI is still stored
    in metadata so retrieval by IRI works either way.
    """
    encoded = urllib.parse.quote(iri, safe="")
    if len(encoded) <= _MAX_KEY_LEN:
        return encoded
    digest = hashlib.sha256(iri.encode("utf-8")).hexdigest()
    return f"h_{digest}"


@dataclass
class StoredArtifact:
    """An artifact retrieved from storage: raw body plus preserved metadata."""

    iri: str
    body: bytes
    partner: str = ""
    type: str = ""
    label: str | None = None
    published_at: str | None = None

    @property
    def metadata(self) -> dict[str, str]:
        meta: dict[str, str] = {"iri": self.iri, "partner": self.partner, "type": self.type}
        if self.label is not None:
            meta["label"] = self.label
        if self.published_at is not None:
            meta["published_at"] = self.published_at
        return meta


@dataclass
class ListEntry:
    """A minimal record returned when enumerating stored artifacts."""

    iri: str
    partner: str = ""
    type: str = ""
    label: str | None = None


@dataclass
class VersionEntry:
    """A single version of an artifact in its history (newest-first listing)."""

    iri: str
    published_at: str
    is_current: bool
    partner: str = ""
    type: str = ""
    label: str | None = None


class StorageBackend(ABC):
    """Abstract storage backend for Linked Art artifacts."""

    @abstractmethod
    def put(
        self,
        iri: str,
        body: bytes,
        *,
        partner: str,
        type: str,
        label: str | None = None,
        published_at: str,
    ) -> str:
        """Store ``body`` as an immutable version of ``iri`` dated ``published_at``.

        Writes a new version object and advances the latest pointer so ``get``
        resolves to it. Returns a ``stored_at`` locator string.
        """

    @abstractmethod
    def get(self, iri: str) -> StoredArtifact | None:
        """Retrieve the current (latest) version of ``iri`` or ``None`` if absent."""

    @abstractmethod
    def get_version(self, iri: str, published_at: str) -> StoredArtifact | None:
        """Retrieve a specific version of ``iri`` verbatim, or ``None`` if absent."""

    @abstractmethod
    def list_versions(self, iri: str) -> list[VersionEntry]:
        """Return all versions of ``iri`` newest-first, the current one flagged.

        Returns an empty list if the IRI is unknown.
        """

    @abstractmethod
    def restore_pointer(self, iri: str, published_at: str | None) -> None:
        """Point ``iri``'s latest at ``published_at`` (or remove it if ``None``).

        Used to roll back a failed publish to the prior current version.
        """

    @abstractmethod
    def delete_version(self, iri: str, published_at: str) -> None:
        """Remove a single version of ``iri`` (no-op if absent)."""

    @abstractmethod
    def delete(self, iri: str) -> None:
        """Remove ``iri`` entirely: all versions plus the latest pointer."""

    @abstractmethod
    def list(self) -> list[ListEntry]:
        """Enumerate all stored artifacts' current versions (metadata only)."""

    @abstractmethod
    def health(self) -> dict[str, object]:
        """Return connectivity/status info for the ``/health`` endpoint."""
