"""Shared test configuration."""

import pytest


@pytest.fixture(autouse=True)
def _hermetic_demo_environment(monkeypatch):
    """Keep demo-launcher settings exported in the shell from changing test behaviour."""
    for key in ("DEMO_PUBLIC_READ", "REPOSITORY_FRONTEND_DIR"):
        monkeypatch.delenv(key, raising=False)
