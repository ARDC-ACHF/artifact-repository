#!/usr/bin/env python3
"""Load the bundled sample artifacts into a running repository instance.

Usage::

    python sample_data/load.py                       # POST to http://localhost:8000
    python sample_data/load.py --base-url http://host:8000
    python sample_data/load.py --direct              # write straight to ./data
    python sample_data/load.py --direct --data-dir /tmp/smoke

HTTP mode sends HTTP Basic credentials read from ``API_AUTH_USERNAME`` and
``API_AUTH_PASSWORD`` (the same variables the server uses).

``--direct`` bypasses HTTP and uses the RepositoryService with filesystem
storage (``<data-dir>/artifacts``) and the SQLite index
(``<data-dir>/index.sqlite3``) — handy for seeding before the server is
started. Stop the server first: it does not coordinate with other writers.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

SAMPLE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SAMPLE_DIR.parent
ARTIFACT_DIR = SAMPLE_DIR / "artifacts"
# Updated variants re-published after the base set to demonstrate snapshotting:
# each shares an ``id`` with a base artifact, so publishing it archives the
# previous version as a dated snapshot. Directories are applied in order.
UPDATE_DIRS = (SAMPLE_DIR / "updates", SAMPLE_DIR / "artifacts_diff_snapshot")


def _iter_artifacts() -> list[dict]:
    artifacts = []
    for path in sorted(ARTIFACT_DIR.glob("*.json")):
        artifacts.append(json.loads(path.read_text(encoding="utf-8")))
    return artifacts


def _iter_updates() -> list[dict]:
    updates = []
    for update_dir in UPDATE_DIRS:
        if update_dir.exists():
            for path in sorted(update_dir.glob("*.json")):
                updates.append(json.loads(path.read_text(encoding="utf-8")))
    return updates


def _auth_header() -> str | None:
    username = os.environ.get("API_AUTH_USERNAME", "")
    password = os.environ.get("API_AUTH_PASSWORD", "")
    if not username or not password:
        return None
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _post_http(base_url: str, auth: str, art: dict) -> tuple[int, dict]:
    body = json.dumps(art).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/v1/artifacts",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": auth},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def load_via_http(base_url: str) -> int:
    auth = _auth_header()
    if auth is None:
        print(
            "Set API_AUTH_USERNAME and API_AUTH_PASSWORD to the server's credentials.",
            file=sys.stderr,
        )
        return 0
    base_url = base_url.rstrip("/")
    ok = 0
    for art in _iter_artifacts():
        try:
            status, data = _post_http(base_url, auth, art)
            print(f"  [{status}] {data['partner']:<10} {data['type']:<16} {data['id']}")
            ok += 1
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"  [{exc.code}] {art.get('id')} -> {detail}", file=sys.stderr)
        except urllib.error.URLError as exc:
            print(
                f"Cannot reach {base_url} ({exc.reason}). Is the server running?",
                file=sys.stderr,
            )
            return ok
    # Re-publish updated variants to create snapshots of the prior versions.
    for art in _iter_updates():
        try:
            _, data = _post_http(base_url, auth, art)
            created = data.get("version_created")
            note = "snapshot created" if created else "unchanged (no snapshot)"
            print(f"  [upd] {data['partner']:<10} {data['type']:<16} {data['id']}  ({note})")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"  [{exc.code}] {art.get('id')} -> {detail}", file=sys.stderr)
        except urllib.error.URLError as exc:
            print(f"Cannot reach {base_url} ({exc.reason}).", file=sys.stderr)
            break
    return ok


def load_direct(data_dir: Path) -> int:
    # Import lazily so HTTP mode has no app dependencies. Running the script by
    # path puts sample_data/ (not the repository root) on sys.path.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from app.index import FtsIndex
    from app.service import RepositoryService, ValidationFailed
    from app.storage.fs_store import FilesystemStore

    index = FtsIndex(data_dir / "index.sqlite3")
    try:
        service = RepositoryService(FilesystemStore(data_dir / "artifacts"), index)
        ok = 0
        for art in _iter_artifacts():
            try:
                resp = service.publish(art)
            except ValidationFailed as exc:
                print(f"  [422] {art.get('id')} -> {exc.result.model_dump_json()}", file=sys.stderr)
                continue
            print(f"  [ok] {resp.partner:<10} {resp.type:<16} {resp.id}")
            ok += 1
        # Re-publish updated variants to create snapshots of the prior versions.
        for art in _iter_updates():
            try:
                resp = service.publish(art)
            except ValidationFailed as exc:
                print(f"  [422] {art.get('id')} -> {exc.result.model_dump_json()}", file=sys.stderr)
                continue
            note = "snapshot created" if resp.version_created else "unchanged (no snapshot)"
            print(f"  [upd] {resp.partner:<10} {resp.type:<16} {resp.id}  ({note})")
        return ok
    finally:
        index.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Write directly to storage/index instead of using HTTP.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Data directory for --direct (default: ./data, as used by the app).",
    )
    args = parser.parse_args()

    total = len(_iter_artifacts())
    print(f"Loading {total} sample artifact(s)…")
    ok = load_direct(args.data_dir) if args.direct else load_via_http(args.base_url)
    print(f"Done: {ok}/{total} loaded.")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
