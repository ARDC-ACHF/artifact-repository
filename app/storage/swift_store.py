"""Swift immutable snapshots and explicit current pointers.

Requires a real swiftclient-compatible connection, injected by the caller.
Single writer per artifact is required: conditional snapshot creation does not
make snapshot/pointer operations distributed transactions. A failed pointer
update may leave a staged snapshot; transport failures may have ambiguous outcomes.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, unquote

from .base import (
    ListEntry, StorageBackend, StoredArtifact, VersionConflictError, VersionEntry,
    iri_to_key, validate_version_id,
)


class SwiftStore(StorageBackend):
    """Versioned objects with single-writer pointer updates."""

    def __init__(self, connection: Any, container: str) -> None:
        self._conn = connection
        self._container = container
        self._conn.put_container(container)

    @staticmethod
    def _version_key(key: str, published_at: str) -> str:
        return f"versions/{key}/{quote(validate_version_id(published_at), safe='')}"

    @staticmethod
    def _pointer_key(key: str) -> str:
        return f"pointers/{key}"

    def _get_object(self, name: str) -> tuple | None:
        try:
            return self._conn.get_object(self._container, name)
        except Exception as exc:
            if getattr(exc, "http_status", None) == 404:
                return None
            raise

    def _delete_object(self, name: str) -> None:
        try:
            self._conn.delete_object(self._container, name)
        except Exception as exc:
            if getattr(exc, "http_status", None) != 404:
                raise

    def _read_pointer(self, key: str) -> str | None:
        result = self._get_object(self._pointer_key(key))
        if result is None:
            return None
        return validate_version_id(result[1].decode("utf-8"))

    def _write_pointer(self, key: str, published_at: str) -> None:
        self._conn.put_object(
            self._container, self._pointer_key(key),
            contents=published_at.encode("utf-8"), headers={"Content-Type": "text/plain"},
        )

    def _version_ids(self, key: str) -> list[str]:
        prefix = f"versions/{key}/"
        _, objects = self._conn.get_container(
            self._container, prefix=prefix, full_listing=True,
        )
        return sorted(
            validate_version_id(unquote(obj["name"][len(prefix):]))
            for obj in objects if obj["name"].startswith(prefix)
        )

    def _read_version(self, key: str, published_at: str) -> StoredArtifact | None:
        result = self._get_object(self._version_key(key, published_at))
        if result is None:
            return None
        headers, body = result
        headers = {name.lower(): value for name, value in headers.items()}
        metadata = {
            name: unquote(headers[f"x-object-meta-{name.replace('_', '-')}"])
            for name in ("iri", "partner", "type", "label", "published_at")
            if f"x-object-meta-{name.replace('_', '-')}" in headers
        }
        return StoredArtifact(body=body, **metadata)

    def put(
        self, iri: str, body: bytes, *, partner: str, type: str,
        label: str | None = None, published_at: str,
    ) -> str:
        key = iri_to_key(iri)
        name = self._version_key(key, published_at)
        artifact = StoredArtifact(iri, body, partner, type, label, published_at)
        headers = {
            f"X-Object-Meta-{field.replace('_', '-').title()}": quote(value, safe="")
            for field, value in artifact.metadata.items()
        }
        headers.update({"Content-Type": "application/ld+json", "If-None-Match": "*"})
        try:
            self._conn.put_object(self._container, name, contents=body, headers=headers)
        except Exception as exc:
            if getattr(exc, "http_status", None) != 412:
                raise
            if self._read_version(key, published_at) != artifact:
                raise VersionConflictError(f"Version already exists: {published_at}") from exc
        self._write_pointer(key, published_at)
        return f"swift://{self._container}/{name}"

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
            self._delete_object(self._pointer_key(key))
        else:
            if self._read_version(key, published_at) is None:
                raise ValueError(f"Version does not exist: {published_at}")
            self._write_pointer(key, published_at)

    def delete_version(self, iri: str, published_at: str) -> None:
        key = iri_to_key(iri)
        name = self._version_key(key, published_at)
        if self._read_pointer(key) == published_at:
            raise ValueError("Cannot delete the current version; restore the pointer first")
        self._delete_object(name)

    def delete(self, iri: str) -> None:
        key = iri_to_key(iri)
        self._delete_object(self._pointer_key(key))
        for published_at in self._version_ids(key):
            self._delete_object(self._version_key(key, published_at))

    def list(self) -> list[ListEntry]:
        _, objects = self._conn.get_container(
            self._container, prefix="pointers/", full_listing=True,
        )
        entries = []
        for obj in objects:
            name = obj["name"]
            if not name.startswith("pointers/"):
                continue
            key = name[len("pointers/"):]
            current = self._read_pointer(key)
            artifact = self._read_version(key, current) if current is not None else None
            if artifact is not None:
                entries.append(ListEntry(
                    artifact.iri, artifact.partner, artifact.type, artifact.label,
                ))
        return entries

    def health(self) -> dict[str, object]:
        from swiftclient.exceptions import ClientException

        try:
            self._conn.head_container(self._container)
        except ClientException as exc:
            return {
                "backend": "swift", "ok": False, "container": self._container,
                "http_status": exc.http_status,
            }
        return {"backend": "swift", "ok": True, "container": self._container}