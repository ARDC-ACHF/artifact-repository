"""Application configuration.

All settings are sourced from environment variables (or a local ``.env`` file)
via pydantic-settings. The service is *local-first*: with no environment
configured at all it runs against a local filesystem storage backend and a
local SQLite index, so ``uvicorn app.main:app`` works on a laptop out of the
box. Switching ``STORAGE_BACKEND`` to ``swift`` (plus Swift credentials) is the
only change required for an OpenStack deployment.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root (…/showcase). Used to derive sensible local defaults.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration for the ingestion service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Storage backend selection ---------------------------------------
    # "fs" (default) => local filesystem, no cloud needed.
    # "swift"        => OpenStack Swift object storage (production).
    storage_backend: Literal["fs", "swift"] = "fs"

    # --- Local filesystem backend ----------------------------------------
    # Directory under which artifacts are written when STORAGE_BACKEND=fs.
    data_dir: Path = _PROJECT_ROOT / "data" / "artifacts"

    # --- SQLite FTS5 search index ----------------------------------------
    index_path: Path = _PROJECT_ROOT / "data" / "index.sqlite3"

    # --- Linked Art JSON-LD context --------------------------------------
    # Bundled offline copy of the context used by the pyld document loader.
    context_path: Path = (
        _PROJECT_ROOT / "app" / "validation" / "context" / "linked-art.json"
    )
    context_url: str = "https://linked.art/ns/v1/linked-art.json"

    # --- OpenStack Swift backend -----------------------------------------
    # Only required when STORAGE_BACKEND=swift.
    swift_container: str = "artifacts"
    os_auth_url: str | None = None
    # Application credential auth (preferred) …
    os_application_credential_id: str | None = None
    os_application_credential_secret: str | None = None
    # … or username/password auth.
    os_username: str | None = None
    os_password: str | None = None
    os_project_name: str | None = None
    os_user_domain_name: str = "Default"
    os_project_domain_name: str = "Default"
    os_region_name: str | None = None

    def ensure_local_dirs(self) -> None:
        """Create local data directories used by the fs backend and index."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
