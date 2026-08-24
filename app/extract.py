"""Extract indexable fields from a Linked Art artifact.

The search index only needs a human-readable ``label`` and a flattened bag of
text (``body_text``) gathered from the common Linked Art string-bearing fields.
This is deliberately simple and tolerant of missing structure.
"""

from __future__ import annotations

from typing import Any

# Fields whose string values are worth indexing for free-text search.
_TEXT_KEYS = ("_label", "content", "value", "label")


def extract_label(payload: dict[str, Any]) -> str | None:
    """Return the artifact's primary human-readable label, if any."""
    label = payload.get("_label")
    if isinstance(label, str) and label.strip():
        return label
    # Some artifacts use identified_by -> Name -> content for the title.
    for entry in _as_list(payload.get("identified_by")):
        if isinstance(entry, dict) and entry.get("type") == "Name":
            content = entry.get("content")
            if isinstance(content, str) and content.strip():
                return content
    return None


def extract_body_text(payload: dict[str, Any]) -> str:
    """Recursively collect string values from indexable fields."""
    parts: list[str] = []
    _collect(payload, parts)
    # De-duplicate while preserving order, then join.
    seen: set[str] = set()
    unique: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return " ".join(unique)


def _collect(node: Any, parts: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _TEXT_KEYS and isinstance(value, str):
                if value.strip():
                    parts.append(value.strip())
            else:
                _collect(value, parts)
    elif isinstance(node, list):
        for item in node:
            _collect(item, parts)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]
