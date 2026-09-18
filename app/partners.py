"""Derive a partner slug from an artifact's IRI.

Partners publish artifacts using their own IRIs (e.g.
``https://ausstage.org.au/event/12345``). We map the IRI host to a short,
stable partner slug used for filtering and display. Unknown hosts fall back to
a slug derived from the registrable-ish host label so new partners still work
without configuration.
"""

from __future__ import annotations

import re
import urllib.parse

# Known host -> partner slug. Extend as partners onboard.
HOST_TO_PARTNER: dict[str, str] = {
    "ausstage.org.au": "ausstage",
    "www.ausstage.org.au": "ausstage",
    "austlit.edu.au": "austlit",
    "www.austlit.edu.au": "austlit",
    "nga.gov.au": "nga",
    "www.nga.gov.au": "nga",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _fallback_slug(host: str) -> str:
    """Build a fallback slug from a host name.

    Strips a leading ``www.`` and slugifies the first remaining host label
    (e.g. ``collections.example.museum`` -> ``collections``). This is a simple,
    predictable rule for unknown partners; known hosts should be added to
    :data:`HOST_TO_PARTNER` for a curated slug.
    """
    host = host.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    labels = [label for label in host.split(".") if label]
    if not labels:
        return "unknown"
    slug = _SLUG_RE.sub("-", labels[0]).strip("-")
    return slug or "unknown"


def partner_for_iri(iri: str) -> str:
    """Return the partner slug for a given artifact IRI."""
    parsed = urllib.parse.urlparse(iri)
    host = (parsed.netloc or "").lower()
    # Strip any userinfo/port.
    host = host.split("@")[-1].split(":")[0]
    if not host:
        return "unknown"
    if host in HOST_TO_PARTNER:
        return HOST_TO_PARTNER[host]
    return _fallback_slug(host)
