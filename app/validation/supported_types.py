"""Supported Linked Art top-level types (pragmatic profile).

This is a deliberately small, curated subset of the Linked Art / CIDOC-CRM
class vocabulary covering the three demo domains plus the shared entities they
reference. Artifacts whose top-level ``type`` is not in this set are rejected
with ``unsupported_type``.
"""

from __future__ import annotations

# Domain-specific top-level classes.
_ART = {"HumanMadeObject"}
_LITERATURE = {"LinguisticObject", "Text"}
_PERFORMANCE = {"Activity", "Event"}

# Shared entities referenced across domains.
_SHARED = {"Person", "Group", "Place", "Set", "VisualItem"}

SUPPORTED_TYPES: frozenset[str] = frozenset(_ART | _LITERATURE | _PERFORMANCE | _SHARED)


def is_supported(type_value: str) -> bool:
    """Return True if ``type_value`` is a supported top-level Linked Art class."""
    return type_value in SUPPORTED_TYPES
