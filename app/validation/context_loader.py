"""Offline JSON-LD document loader for pyld.

pyld would otherwise fetch ``@context`` URLs over the network on every
expansion. This loader serves the bundled Linked Art context from disk and
refuses any other remote fetch, so validation is fully offline and
deterministic at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from pyld import jsonld


def build_document_loader(context_url: str, context_path: Path) -> Callable[..., dict]:
    """Return a pyld document loader bound to a bundled local context.

    Requests for exactly ``context_url``
    return the on-disk context; any other URL raises a JSON-LD load error.
    """
    context_doc = json.loads(Path(context_path).read_text(encoding="utf-8"))

    def loader(url: str, options: dict[str, Any] | None = None) -> dict:
        if url == context_url:
            return {
                "contextUrl": None,
                "documentUrl": url,
                "document": context_doc,
            }
        raise jsonld.JsonLdError(
            "Remote context loading is disabled (offline validation).",
            "jsonld.LoadDocumentError",
            {"url": url},
            code="loading remote context failed",
        )

    return loader
