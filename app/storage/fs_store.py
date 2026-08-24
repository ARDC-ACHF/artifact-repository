"""Local filesystem storage backend (default for laptop / demo runs).

Artifacts are stored *versioned*. For each IRI (encoded to ``<key>`` via
:func:`iri_to_key`) the layout under ``settings.data_dir`` is::

    versions/<key>/<published_at>.jsonld     # immutable version body, verbatim
    versions/<key>/<published_at>.meta.json  # preserved metadata for the version
    <key>.latest.json                        # pointer: {"published_at": "…"}

``<published_at>`` is the URL-encoded UTC publication timestamp (its ``:`` are
percent-encoded so it is a valid filename). The ``<key>.latest.json`` pointer
records which version is current, so ``get(iri)`` returns the latest version
verbatim. Older versions remain on disk as immutable, retrievable snapshots.

Legacy flat-layout data (``<key>.jsonld`` written before versioning) is still
readable: ``get`` falls back to it when no versions/pointer exist.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

from app.config import Settings
from app.storage.base import (
    ListEntry,
    StorageBackend,
    StoredArtifact,
    VersionEntry,
    iri_to_key,
)

_LATEST_SUFFIX = ".latest.json"


class FilesystemStore(StorageBackend):
    """Stores artifacts as versioned files in a local directory."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._dir: Path = settings.data_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    # --- path helpers ----------------------------------------------------
    def _versions_dir(self, key: str) -> Path:
        return self._dir / "versions" / key

    def _version_body_path(self, key: str, published_at: str) -> Path:
        enc = urllib.parse.quote(published_at, safe="")
        return self._versions_dir(key) / f"{enc}.jsonld"

    def _version_meta_path(self, key: str, published_at: str) -> Path:
        enc = urllib.parse.quote(published_at, safe="")
        return self._versions_dir(key) / f"{enc}.meta.json"

    def _pointer_path(self, key: str) -> Path:
        return self._dir / f"{key}{_LATEST_SUFFIX}"

    # legacy flat layout (pre-versioning)
    def _legacy_body_path(self, key: str) -> Path:
        return self._dir / f"{key}.jsonld"

    def _legacy_meta_path(self, key: str) -> Path:
        return self._dir / f"{key}.meta.json"

    # --- pointer helpers -------------------------------------------------
    def _read_pointer(self, key: str) -> str | None:
        path = self._pointer_path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        pa = data.get("published_at")
        return str(pa) if pa else None

    def _write_pointer(self, key: str, published_at: str) -> None:
        self._pointer_path(key).write_text(
            json.dumps({"published_at": published_at}), encoding="utf-8"
        )

    def _version_ids(self, key: str) -> list[str]:
        """All version publication dates for ``key``, sorted oldest→newest."""
        vdir = self._versions_dir(key)
        if not vdir.exists():
            return []
        ids: list[str] = []
        for meta_path in vdir.glob("*.meta.json"):
            enc = meta_path.name[: -len(".meta.json")]
            ids.append(urllib.parse.unquote(enc))
        # ISO-8601 UTC timestamps sort correctly as plain strings.
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
        self._versions_dir(key).mkdir(parents=True, exist_ok=True)
        meta = {
            "iri": iri,
            "partner": partner,
            "type": type,
            "label": label,
            "published_at": published_at,
        }
        # Write the immutable version (meta then body), then advance the
        # pointer so a partial write never becomes the visible "current".
        self._version_meta_path(key, published_at).write_text(
            json.dumps(meta), encoding="utf-8"
        )
        self._version_body_path(key, published_at).write_bytes(body)
        self._write_pointer(key, published_at)
        return f"file://{self._version_body_path(key, published_at)}"

    # --- reads -----------------------------------------------------------
    def _read_version(
        self, iri: str, key: str, published_at: str
    ) -> StoredArtifact | None:
        body_path = self._version_body_path(key, published_at)
        if not body_path.exists():
            return None
        body = body_path.read_bytes()
        meta: dict[str, object] = {}
        meta_path = self._version_meta_path(key, published_at)
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return StoredArtifact(
            iri=str(meta.get("iri", iri)),
            body=body,
            partner=str(meta.get("partner", "")),
            type=str(meta.get("type", "")),
            label=meta.get("label") if meta.get("label") is not None else None,  # type: ignore[arg-type]
            published_at=str(meta.get("published_at", published_at)),
        )

    def _read_legacy(self, iri: str, key: str) -> StoredArtifact | None:
        body_path = self._legacy_body_path(key)
        if not body_path.exists():
            return None
        body = body_path.read_bytes()
        meta: dict[str, object] = {}
        meta_path = self._legacy_meta_path(key)
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return StoredArtifact(
            iri=str(meta.get("iri", iri)),
            body=body,
            partner=str(meta.get("partner", "")),
            type=str(meta.get("type", "")),
            label=meta.get("label") if meta.get("label") is not None else None,  # type: ignore[arg-type]
            published_at=meta.get("published_at"),  # type: ignore[arg-type]
        )

    def get(self, iri: str) -> StoredArtifact | None:
        key = iri_to_key(iri)
        # 1) pointer → current version
        pa = self._read_pointer(key)
        if pa is not None:
            art = self._read_version(iri, key, pa)
            if art is not None:
                return art
        # 2) no/broken pointer: fall back to the newest version on disk
        ids = self._version_ids(key)
        if ids:
            return self._read_version(iri, key, ids[-1])
        # 3) legacy flat layout
        return self._read_legacy(iri, key)

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
        # Newest first.
        for pa in reversed(ids):
            meta: dict[str, object] = {}
            meta_path = self._version_meta_path(key, pa)
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    meta = {}
            entries.append(
                VersionEntry(
                    iri=str(meta.get("iri", iri)),
                    published_at=pa,
                    is_current=(pa == current),
                    partner=str(meta.get("partner", "")),
                    type=str(meta.get("type", "")),
                    label=meta.get("label") if meta.get("label") is not None else None,  # type: ignore[arg-type]
                )
            )
        return entries

    # --- rollback / deletion --------------------------------------------
    def restore_pointer(self, iri: str, published_at: str | None) -> None:
        key = iri_to_key(iri)
        if published_at is None:
            self._pointer_path(key).unlink(missing_ok=True)
        else:
            self._write_pointer(key, published_at)

    def delete_version(self, iri: str, published_at: str) -> None:
        key = iri_to_key(iri)
        self._version_body_path(key, published_at).unlink(missing_ok=True)
        self._version_meta_path(key, published_at).unlink(missing_ok=True)

    def delete(self, iri: str) -> None:
        key = iri_to_key(iri)
        vdir = self._versions_dir(key)
        if vdir.exists():
            for child in vdir.iterdir():
                child.unlink(missing_ok=True)
            vdir.rmdir()
        self._pointer_path(key).unlink(missing_ok=True)
        # Legacy flat files, if any.
        self._legacy_body_path(key).unlink(missing_ok=True)
        self._legacy_meta_path(key).unlink(missing_ok=True)

    # --- enumeration -----------------------------------------------------
    def list(self) -> list[ListEntry]:
        entries: list[ListEntry] = []
        seen_keys: set[str] = set()
        # Current versions, resolved via pointers.
        for ptr_path in sorted(self._dir.glob(f"*{_LATEST_SUFFIX}")):
            key = ptr_path.name[: -len(_LATEST_SUFFIX)]
            seen_keys.add(key)
            iri_guess = ""
            pa = self._read_pointer(key)
            if pa is None:
                ids = self._version_ids(key)
                pa = ids[-1] if ids else None
            if pa is None:
                continue
            art = self._read_version(iri_guess, key, pa)
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
        # Legacy flat metas with no pointer.
        for meta_path in sorted(self._dir.glob("*.meta.json")):
            key = meta_path.name[: -len(".meta.json")]
            if key in seen_keys:
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            entries.append(
                ListEntry(
                    iri=str(meta.get("iri", "")),
                    partner=str(meta.get("partner", "")),
                    type=str(meta.get("type", "")),
                    label=meta.get("label"),
                )
            )
        return entries

    def health(self) -> dict[str, object]:
        ok = self._dir.exists() and self._dir.is_dir()
        return {
            "backend": "fs",
            "ok": ok,
            "data_dir": str(self._dir),
        }
