"""Repository service: orchestrates validation, storage and indexing.

This is the single place where an ingest is coordinated so both the HTTP API
and the sample-data loader share identical behaviour. Storage is the source of
truth; the FTS index is a rebuildable projection kept consistent per request.
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from app.config import Settings
from app.extract import extract_body_text, extract_label
from app.index import FtsIndex, IndexRecord
from app.models import (
    ArtifactSummary,
    ArtifactVersion,
    PublishResponse,
    ValidationResult,
    VersionListResponse,
)
from app.partners import partner_for_iri
from app.storage import StorageBackend, StoredArtifact
from app.storage.base import VersionEntry
from app.validation import LinkedArtValidator


class ValidationFailed(Exception):
    """Raised when an artifact fails validation during publish."""

    def __init__(self, result: ValidationResult) -> None:
        super().__init__("Artifact failed validation")
        self.result = result


def locator_for(iri: str) -> str:
    """Build the canonical repository locator for an IRI."""
    return f"/api/v1/artifacts/{urllib.parse.quote(iri, safe='')}"


def version_locator_for(iri: str, published_at: str) -> str:
    """Build the locator for a specific version of an IRI."""
    return (
        f"/api/v1/artifacts/{urllib.parse.quote(iri, safe='')}"
        f"/versions/{urllib.parse.quote(published_at, safe='')}"
    )


def _canonical(payload: Any) -> str:
    """Canonical JSON (sorted keys) so content equality ignores key ordering."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _now_published_at() -> str:
    """Server-stamped UTC publication date, microsecond precision, ``…Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


class RepositoryService:
    """Coordinates the ingest/query lifecycle over storage + index."""

    def __init__(
        self,
        settings: Settings,
        storage: StorageBackend,
        index: FtsIndex,
        validator: LinkedArtValidator | None = None,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._index = index
        self._validator = validator or LinkedArtValidator(
            settings.context_url, settings.context_path
        )

    # --- validation ------------------------------------------------------
    def validate(self, payload: Any) -> ValidationResult:
        return self._validator.validate(payload)

    # --- publish ---------------------------------------------------------
    def publish(self, payload: Any) -> PublishResponse:
        """Validate then store+index an artifact with change-triggered snapshots.

        Re-publishing an IRI whose canonical content differs from the current
        version writes a new immutable version (the prior version is retained
        as a dated snapshot). An identical re-publish is an idempotent no-op
        (``version_created=False``). Raises :class:`ValidationFailed` if the
        artifact is invalid.
        """
        result = self._validator.validate(payload)
        if not result.valid:
            raise ValidationFailed(result)

        iri: str = payload["id"]
        type_: str = payload["type"]
        partner = partner_for_iri(iri)
        label = extract_label(payload)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        current = self._storage.get(iri)

        # Idempotent re-publish: identical content => no new version/snapshot.
        if current is not None and self._same_content(current, payload):
            return PublishResponse(
                id=iri,
                locator=locator_for(iri),
                partner=partner,
                type=type_,
                stored_at=version_locator_for(
                    iri, current.published_at or ""
                ),
                published_at=current.published_at or "",
                version_created=False,
                snapshot_of=None,
            )

        prior_published_at = current.published_at if current is not None else None
        published_at = self._unique_published_at(iri)

        # Write the new immutable version (advances the latest pointer), then
        # index the current version only. If indexing fails, roll the pointer
        # back to the prior version and drop the just-written version so the
        # two never diverge for this request.
        stored_at = self._storage.put(
            iri,
            body,
            partner=partner,
            type=type_,
            label=label,
            published_at=published_at,
        )
        try:
            self._index.upsert(
                iri,
                partner=partner,
                type=type_,
                label=label,
                body_text=extract_body_text(payload),
            )
        except Exception:
            self._storage.restore_pointer(iri, prior_published_at)
            self._storage.delete_version(iri, published_at)
            raise

        return PublishResponse(
            id=iri,
            locator=locator_for(iri),
            partner=partner,
            type=type_,
            stored_at=stored_at,
            published_at=published_at,
            version_created=True,
            snapshot_of=prior_published_at,
        )

    @staticmethod
    def _same_content(current: StoredArtifact, payload: Any) -> bool:
        """True if ``payload`` is canonically identical to the current body."""
        try:
            current_obj = json.loads(current.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False
        return _canonical(current_obj) == _canonical(payload)

    def _unique_published_at(self, iri: str) -> str:
        """A publication date not already used by a version of ``iri``.

        Microsecond precision makes collisions unlikely; a counter suffix is
        appended in the rare case two *changed* publishes share a timestamp.
        """
        base = _now_published_at()
        candidate = base
        counter = 1
        while self._storage.get_version(iri, candidate) is not None:
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    # --- retrieval / listing / search -----------------------------------
    def get_current(self, iri: str) -> StoredArtifact | None:
        """Return the current version (body + metadata) or ``None``."""
        return self._storage.get(iri)

    def get_raw(self, iri: str) -> bytes | None:
        stored = self._storage.get(iri)
        return stored.body if stored is not None else None

    def get_version_raw(self, iri: str, published_at: str) -> bytes | None:
        """Return a specific version's body verbatim, or ``None`` if absent."""
        stored = self._storage.get_version(iri, published_at)
        return stored.body if stored is not None else None

    def list_versions(self, iri: str) -> VersionListResponse | None:
        """Return the version history of ``iri`` (newest first), or ``None``.

        ``None`` signals an unknown IRI (no versions stored).
        """
        versions = self._storage.list_versions(iri)
        if not versions:
            return None
        return VersionListResponse(
            id=iri,
            total=len(versions),
            versions=[self._to_version(iri, v) for v in versions],
        )

    def list(
        self,
        *,
        partner: str | None = None,
        type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[ArtifactSummary]]:
        total, records = self._index.list(
            types=[type] if type else None,
            partners=[partner] if partner else None,
            limit=limit,
            offset=offset,
        )
        return total, [self._to_summary(r) for r in records]

    def search(
        self,
        q: str,
        *,
        types: list[str] | None = None,
        partners: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[ArtifactSummary]]:
        total, records = self._index.search(
            q, types=types, partners=partners, limit=limit, offset=offset
        )
        return total, [self._to_summary(r) for r in records]

    # --- maintenance -----------------------------------------------------
    def reindex(self) -> int:
        """Rebuild the FTS index entirely from the storage backend."""
        self._index.clear()
        count = 0
        for entry in self._storage.list():
            stored = self._storage.get(entry.iri)
            if stored is None:
                continue
            try:
                payload = json.loads(stored.body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = {}
            self._index.upsert(
                entry.iri,
                partner=entry.partner,
                type=entry.type,
                label=entry.label,
                body_text=extract_body_text(payload) if payload else "",
            )
            count += 1
        return count

    @staticmethod
    def _to_summary(record: IndexRecord) -> ArtifactSummary:
        return ArtifactSummary(
            id=record.iri,
            type=record.type,
            partner=record.partner,
            label=record.label,
            locator=locator_for(record.iri),
        )

    @staticmethod
    def _to_version(iri: str, entry: VersionEntry) -> ArtifactVersion:
        return ArtifactVersion(
            published_at=entry.published_at,
            is_current=entry.is_current,
            type=entry.type,
            partner=entry.partner,
            label=entry.label,
            locator=version_locator_for(iri, entry.published_at),
        )
