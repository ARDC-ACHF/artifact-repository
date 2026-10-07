"""Derive a partner slug from an artifact's IRI.

Partners publish artifacts using their own IRIs (e.g.
``https://ausstage.org.au/event/12345``). We map the IRI host to a short,
stable partner slug used for filtering and display. Unknown hosts fall back to
a slug derived from the registrable domain label so new partners still work
without configuration.
"""

from __future__ import annotations

import re
import urllib.parse

import tldextract

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
# Use the bundled Public Suffix List without network requests or a disk cache.
_EXTRACT_DOMAIN = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


def _fallback_slug(host: str) -> str:
    """Build a fallback slug from a host name.

    Ignore subdomains and public suffixes (including multi-label suffixes such
    as ``net.au``): ``api.acmi.net.au`` -> ``acmi`` and
    ``collections.example.museum`` -> ``example``. For unrecognised suffixes,
    retain the first-label fallback. Known hosts can override this convention
    through :data:`HOST_TO_PARTNER`.
    """
    host = host.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    labels = [label for label in host.split(".") if label]
    if not labels:
        return "unknown"
    extracted = _EXTRACT_DOMAIN(host)
    label = extracted.domain if extracted.suffix else labels[0]
    slug = _SLUG_RE.sub("-", label).strip("-")
    return slug or "unknown"


def partner_for_iri(iri: str) -> str:
    """Return the partner slug for a given artifact IRI."""
    parsed = urllib.parse.urlparse(iri)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return "unknown"
    if host in HOST_TO_PARTNER:
        return HOST_TO_PARTNER[host]
    return _fallback_slug(host)
