"""Shared pytest fixtures.

All tests run against the local filesystem storage backend and a temporary
SQLite index, so no Swift/OpenStack access is required. Sample artifacts in
``sample_data/artifacts`` are reused as fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = PROJECT_ROOT / "sample_data" / "artifacts"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Fresh Settings pointing storage + index at a temp directory."""
    monkeypatch.setenv("STORAGE_BACKEND", "fs")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("INDEX_PATH", str(tmp_path / "index.sqlite3"))

    from app.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    s.ensure_local_dirs()
    yield s
    get_settings.cache_clear()


@pytest.fixture
def validator(settings):
    from app.validation import LinkedArtValidator

    return LinkedArtValidator(settings.context_url, settings.context_path)


@pytest.fixture
def sample_artifacts() -> dict[str, dict]:
    """All sample artifacts, keyed by filename stem."""
    out: dict[str, dict] = {}
    for path in sorted(SAMPLE_DIR.glob("*.json")):
        out[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return out


@pytest.fixture
def client(settings):
    """A FastAPI TestClient wired to the temp fs backend + index."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
