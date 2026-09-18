"""Filesystem snapshots as atomic JSON envelopes containing base64 raw bytes.

Layout: versions/<hashed-iri>/<quoted-timestamp>.json and <hashed-iri>.latest.json.
Complete records are linked exclusively into place before atomic pointer
replacement. Single writer per artifact is required; this is not a transaction
across records. Failed publication can leave staged snapshots for cleanup.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote

from .base import (
    ListEntry, StorageBackend, StoredArtifact, VersionConflictError, VersionEntry,
    iri_to_key, validate_version_id,
)

_LATEST_SUFFIX = ".latest.json"


class FilesystemStore(StorageBackend):
    """Local single-writer storage with immutable, complete version records."""

    def __init__(self, data_dir: Path) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _versions_dir(self, key: str) -> Path:
        return self._dir / "versions" / key

    def _version_path(self, key: str, published_at: str) -> Path:
        return self._versions_dir(key) / f"{quote(validate_version_id(published_at), safe='')}.json"

    def _pointer_path(self, key: str) -> Path:
        return self._dir / f"{key}{_LATEST_SUFFIX}"

    @staticmethod
    def _write_json(path: Path, data: dict, *, exclusive: bool = False) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, prefix=".staged-", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            if exclusive:
                os.link(temporary, path)
            else:
                os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _read_pointer(self, key: str) -> str | None:
        try:
            text = self._pointer_path(key).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return validate_version_id(json.loads(text)["published_at"])

    def _write_pointer(self, key: str, published_at: str) -> None:
        self._write_json(self._pointer_path(key), {"published_at": published_at})

    def _read_version(self, key: str, published_at: str) -> StoredArtifact | None:
        try:
            text = self._version_path(key, published_at).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        record = json.loads(text)
        return StoredArtifact(
            body=base64.b64decode(record["body"], validate=True), **record["metadata"],
        )

    def _version_ids(self, key: str) -> list[str]:
        return sorted(
            validate_version_id(unquote(path.stem))
            for path in self._versions_dir(key).glob("*.json")
        )

    def put(
        self, iri: str, body: bytes, *, partner: str, type: str,
        label: str | None = None, published_at: str,
    ) -> str:
        key = iri_to_key(iri)
        path = self._version_path(key, published_at)
        artifact = StoredArtifact(iri, body, partner, type, label, published_at)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._write_json(path, {
                "body": base64.b64encode(body).decode("ascii"),
                "metadata": artifact.metadata,
            }, exclusive=True)
        except FileExistsError:
            if self._read_version(key, published_at) != artifact:
                raise VersionConflictError(f"Version already exists: {published_at}") from None
        self._write_pointer(key, published_at)
        return path.absolute().as_uri()

    def get(self, iri: str) -> StoredArtifact | None:
        key = iri_to_key(iri)
        current = self._read_pointer(key)
        return self._read_version(key, current) if current is not None else None

    def get_version(self, iri: str, published_at: str) -> StoredArtifact | None:
        return self._read_version(iri_to_key(iri), published_at)

    def list_versions(self, iri: str) -> list[VersionEntry]:
        key = iri_to_key(iri)
        current = self._read_pointer(key)
        entries = []
        for published_at in reversed(self._version_ids(key)):
            artifact = self._read_version(key, published_at)
            if artifact is not None:
                entries.append(VersionEntry(
                    artifact.iri, published_at, published_at == current,
                    artifact.partner, artifact.type, artifact.label,
                ))
        return entries

    def restore_pointer(self, iri: str, published_at: str | None) -> None:
        key = iri_to_key(iri)
        if published_at is None:
            self._pointer_path(key).unlink(missing_ok=True)
        else:
            if self._read_version(key, published_at) is None:
                raise ValueError(f"Version does not exist: {published_at}")
            self._write_pointer(key, published_at)

    def delete_version(self, iri: str, published_at: str) -> None:
        key = iri_to_key(iri)
        path = self._version_path(key, published_at)
        if self._read_pointer(key) == published_at:
            raise ValueError("Cannot delete the current version; restore the pointer first")
        path.unlink(missing_ok=True)

    def delete(self, iri: str) -> None:
        key = iri_to_key(iri)
        self._pointer_path(key).unlink(missing_ok=True)
        for published_at in self._version_ids(key):
            self._version_path(key, published_at).unlink(missing_ok=True)

    def list(self) -> list[ListEntry]:
        entries = []
        for path in sorted(self._dir.glob(f"*{_LATEST_SUFFIX}")):
            key = path.name[:-len(_LATEST_SUFFIX)]
            current = self._read_pointer(key)
            artifact = self._read_version(key, current) if current is not None else None
            if artifact is not None:
                entries.append(ListEntry(
                    artifact.iri, artifact.partner, artifact.type, artifact.label,
                ))
        return entries

    def health(self) -> dict[str, object]:
        return {"backend": "fs", "ok": self._dir.is_dir(), "data_dir": str(self._dir)}
