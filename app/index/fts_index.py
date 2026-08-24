"""SQLite FTS5 full-text search index.

The index is a secondary, rebuildable projection of the artifacts stored in the
authoritative storage backend. It holds just enough per artifact — IRI, partner,
type, label and a flattened ``body_text`` — to power cross-domain free-text
search plus ``partner``/``type`` filtering.

The index is *not* the source of truth: :meth:`reindex` can rebuild it entirely
from the storage backend if the two ever diverge.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class IndexRecord:
    """A row returned from the index."""

    iri: str
    partner: str
    type: str
    label: str | None


def _quote_fts_query(q: str) -> str:
    """Turn arbitrary user input into a safe FTS5 MATCH expression.

    Each whitespace-separated token is wrapped in double quotes (escaping any
    embedded quotes) and given a prefix ``*`` so partial words match. This
    avoids FTS5 syntax errors from user-supplied punctuation.
    """
    tokens = [t for t in q.replace('"', " ").split() if t]
    if not tokens:
        return '""'
    return " ".join(f'"{t}"*' for t in tokens)


class FtsIndex:
    """A thin wrapper around a SQLite FTS5 ``artifacts`` table."""

    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        # check_same_thread=False + a lock: FastAPI may touch this from
        # different threads; writes are serialized by the lock.
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS artifacts
                USING fts5(iri, partner, type, label, body_text);
                """
            )

    # --- writes ----------------------------------------------------------
    def upsert(
        self,
        iri: str,
        *,
        partner: str,
        type: str,
        label: str | None,
        body_text: str,
    ) -> None:
        """Insert or replace the index entry for ``iri`` (deterministic)."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM artifacts WHERE iri = ?", (iri,))
            self._conn.execute(
                "INSERT INTO artifacts (iri, partner, type, label, body_text) "
                "VALUES (?, ?, ?, ?, ?)",
                (iri, partner, type, label or "", body_text),
            )

    def delete(self, iri: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM artifacts WHERE iri = ?", (iri,))

    def clear(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM artifacts")

    # --- reads -----------------------------------------------------------
    def search(
        self,
        q: str,
        *,
        types: list[str] | None = None,
        partners: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[IndexRecord]]:
        """Full-text search with optional type/partner filters.

        Returns ``(total_matches, page_of_records)``.
        """
        match = _quote_fts_query(q)
        where = ["artifacts MATCH ?"]
        params: list[object] = [match]
        self._append_filters(where, params, types, partners)
        where_sql = " AND ".join(where)

        total = self._count(where_sql, params)
        rows = self._conn.execute(
            f"SELECT iri, partner, type, label FROM artifacts "
            f"WHERE {where_sql} ORDER BY rank LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return total, [self._row(r) for r in rows]

    def list(
        self,
        *,
        types: list[str] | None = None,
        partners: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[IndexRecord]]:
        """List entries (no free-text) with optional filters and paging."""
        where: list[str] = []
        params: list[object] = []
        self._append_filters(where, params, types, partners)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        total = self._count(where_sql.replace(" WHERE ", "", 1) or "1=1", params)
        rows = self._conn.execute(
            f"SELECT iri, partner, type, label FROM artifacts{where_sql} "
            f"ORDER BY iri LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return total, [self._row(r) for r in rows]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM artifacts").fetchone()
        return int(row["c"])

    def health(self) -> dict[str, object]:
        try:
            n = self.count()
            return {"ok": True, "path": self._path, "count": n}
        except sqlite3.Error as exc:  # pragma: no cover - defensive
            return {"ok": False, "path": self._path, "error": str(exc)}

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- helpers ---------------------------------------------------------
    @staticmethod
    def _append_filters(
        where: list[str],
        params: list[object],
        types: list[str] | None,
        partners: list[str] | None,
    ) -> None:
        if types:
            placeholders = ",".join("?" for _ in types)
            where.append(f"type IN ({placeholders})")
            params.extend(types)
        if partners:
            placeholders = ",".join("?" for _ in partners)
            where.append(f"partner IN ({placeholders})")
            params.extend(partners)

    def _count(self, where_sql: str, params: list[object]) -> int:
        row = self._conn.execute(
            f"SELECT COUNT(*) AS c FROM artifacts WHERE {where_sql}", params
        ).fetchone()
        return int(row["c"])

    @staticmethod
    def _row(r: sqlite3.Row) -> IndexRecord:
        return IndexRecord(
            iri=r["iri"],
            partner=r["partner"],
            type=r["type"],
            label=r["label"] or None,
        )
