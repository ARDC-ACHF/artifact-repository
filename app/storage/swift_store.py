"""OpenStack Swift storage backend (production).

Artifacts are stored *versioned*. For each IRI (encoded to ``<key>`` via
:func:`iri_to_key`) the container holds:

* version objects at ``versions/<key>/<published_at>`` — one immutable object
  per version, with the raw IRI, partner, type, label and publication date in
  ``X-Object-Meta-*`` headers.
* a pointer object at ``pointers/<key>`` whose body is the current version's
  ``published_at`` timestamp.

``get(iri)`` reads the pointer then the referenced version object, so the
current version is returned verbatim. Older versions remain retrievable as
immutable snapshots via ``get_version`` / ``list_versions``.

``python-swiftclient`` is imported lazily so the module only requires Swift
libraries when ``STORAGE_BACKEND=swift`` is actually selected.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from app.config import Settings
from app.storage.base import (
    ListEntry,
    StorageBackend,
    StoredArtifact,
    VersionEntry,
    iri_to_key,
)


class SwiftStore(StorageBackend):
    """Stores artifacts as versioned objects in an OpenStack Swift container."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._container = settings.swift_container
        self._conn = self._build_connection(settings)
        self._ensure_container()

    @staticmethod
    def _build_connection(settings: Settings) -> Any:
        from swiftclient.client import Connection

        os_options: dict[str, Any] = {
            "user_domain_name": settings.os_user_domain_name,
            "project_domain_name": settings.os_project_domain_name,
        }
        if settings.os_project_name:
            os_options["project_name"] = settings.os_project_name
        if settings.os_region_name:
            os_options["region_name"] = settings.os_region_name

        # Prefer application-credential auth when provided.
        if settings.os_application_credential_id and settings.os_application_credential_secret:
            os_options["application_credential_id"] = settings.os_application_credential_id
            os_options["application_credential_secret"] = (
                settings.os_application_credential_secret
            )
            return Connection(
                authurl=settings.os_auth_url,
                auth_version="3",
                os_options=os_options,
            )

        return Connection(
            authurl=settings.os_auth_url,
            user=settings.os_username,
            key=settings.os_password,
            auth_version="3",
            os_options=os_options,
        )

    def _ensure_container(self) -> None:
        try:
            self._conn.put_container(self._container)
        except Exception:
            # Container may already exist or auth may be deferred; surfaced by health().
            pass

    # --- key helpers -----------------------------------------------------
    @staticmethod
    def _version_key(key: str, published_at: str) -> str:
        enc = urllib.parse.quote(published_at, safe="")
        return f"versions/{key}/{enc}"

    @staticmethod
    def _versions_prefix(key: str) -> str:
        return f"versions/{key}/"

    @staticmethod
    def _pointer_key(key: str) -> str:
        return f"pointers/{key}"

    # --- pointer helpers -------------------------------------------------
    def _read_pointer(self, key: str) -> str | None:
        from swiftclient.exceptions import ClientException

        try:
            _, body = self._conn.get_object(self._container, self._pointer_key(key))
        except ClientException as exc:
            if getattr(exc, "http_status", None) == 404:
                return None
            raise
        text = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else str(body)
        text = text.strip()
        return text or None

    def _write_pointer(self, key: str, published_at: str) -> None:
        self._conn.put_object(
            self._container,
            self._pointer_key(key),
            contents=published_at.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
        )

    def _version_ids(self, key: str) -> list[str]:
        """All version publication dates for ``key``, sorted oldest→newest."""
        _, objects = self._conn.get_container(
            self._container, prefix=self._versions_prefix(key), full_listing=True
        )
        ids: list[str] = []
        prefix = self._versions_prefix(key)
        for obj in objects:
            name = obj.get("name", "")
            if not name.startswith(prefix):
                continue
            enc = name[len(prefix) :]
            if enc:
                ids.append(urllib.parse.unquote(enc))
        return sorted(ids)

    # --- writes ----------------------------------------------------------
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
        key = iri_to_key(iri)
        headers = {
            "X-Object-Meta-Iri": iri,
            "X-Object-Meta-Partner": partner,
            "X-Object-Meta-Type": type,
            "X-Object-Meta-Published-At": published_at,
            "Content-Type": "application/ld+json",
        }
        if label is not None:
            headers["X-Object-Meta-Label"] = label
        version_key = self._version_key(key, published_at)
        self._conn.put_object(
            self._container,
            version_key,
            contents=body,
            headers=headers,
        )
        self._write_pointer(key, published_at)
        return f"swift://{self._container}/{version_key}"

    # --- reads -----------------------------------------------------------
    def _read_version(
        self, iri: str, key: str, published_at: str
    ) -> StoredArtifact | None:
        from swiftclient.exceptions import ClientException

        try:
            headers, body = self._conn.get_object(
                self._container, self._version_key(key, published_at)
            )
        except ClientException as exc:
            if getattr(exc, "http_status", None) == 404:
                return None
            raise
        return StoredArtifact(
            iri=headers.get("x-object-meta-iri", iri),
            body=body,
            partner=headers.get("x-object-meta-partner", ""),
            type=headers.get("x-object-meta-type", ""),
            label=headers.get("x-object-meta-label"),
            published_at=headers.get("x-object-meta-published-at", published_at),
        )

    def get(self, iri: str) -> StoredArtifact | None:
        key = iri_to_key(iri)
        pa = self._read_pointer(key)
        if pa is not None:
            art = self._read_version(iri, key, pa)
            if art is not None:
                return art
        ids = self._version_ids(key)
        if ids:
            return self._read_version(iri, key, ids[-1])
        return None

    def get_version(self, iri: str, published_at: str) -> StoredArtifact | None:
        key = iri_to_key(iri)
        return self._read_version(iri, key, published_at)

    def list_versions(self, iri: str) -> list[VersionEntry]:
        key = iri_to_key(iri)
        ids = self._version_ids(key)
        if not ids:
            return []
        current = self._read_pointer(key) or ids[-1]
        entries: list[VersionEntry] = []
        for pa in reversed(ids):
            try:
                headers = self._conn.head_object(
                    self._container, self._version_key(key, pa)
                )
            except Exception:
                headers = {}
            entries.append(
                VersionEntry(
                    iri=headers.get("x-object-meta-iri", iri),
                    published_at=pa,
                    is_current=(pa == current),
                    partner=headers.get("x-object-meta-partner", ""),
                    type=headers.get("x-object-meta-type", ""),
                    label=headers.get("x-object-meta-label"),
                )
            )
        return entries

    # --- rollback / deletion --------------------------------------------
    def restore_pointer(self, iri: str, published_at: str | None) -> None:
        from swiftclient.exceptions import ClientException

        key = iri_to_key(iri)
        if published_at is None:
            try:
                self._conn.delete_object(self._container, self._pointer_key(key))
            except ClientException as exc:
                if getattr(exc, "http_status", None) != 404:
                    raise
        else:
            self._write_pointer(key, published_at)

    def delete_version(self, iri: str, published_at: str) -> None:
        from swiftclient.exceptions import ClientException

        key = iri_to_key(iri)
        try:
            self._conn.delete_object(
                self._container, self._version_key(key, published_at)
            )
        except ClientException as exc:
            if getattr(exc, "http_status", None) != 404:
                raise

    def delete(self, iri: str) -> None:
        from swiftclient.exceptions import ClientException

        key = iri_to_key(iri)
        for pa in self._version_ids(key):
            self.delete_version(iri, pa)
        try:
            self._conn.delete_object(self._container, self._pointer_key(key))
        except ClientException as exc:
            if getattr(exc, "http_status", None) != 404:
                raise

    # --- enumeration -----------------------------------------------------
    def list(self) -> list[ListEntry]:
        entries: list[ListEntry] = []
        _, objects = self._conn.get_container(
            self._container, prefix="pointers/", full_listing=True
        )
        for obj in objects:
            name = obj.get("name", "")
            key = name[len("pointers/") :]
            if not key:
                continue
            pa = self._read_pointer(key)
            if pa is None:
                ids = self._version_ids(key)
                pa = ids[-1] if ids else None
            if pa is None:
                continue
            art = self._read_version("", key, pa)
            if art is None:
                continue
            entries.append(
                ListEntry(
                    iri=art.iri,
                    partner=art.partner,
                    type=art.type,
                    label=art.label,
                )
            )
        return entries

    def health(self) -> dict[str, object]:
        try:
            self._conn.head_container(self._container)
            return {"backend": "swift", "ok": True, "container": self._container}
        except Exception as exc:  # pragma: no cover - depends on live Swift
            return {
                "backend": "swift",
                "ok": False,
                "container": self._container,
                "error": str(exc),
            }
