#!/usr/bin/env python3
"""Load the bundled sample artifacts into a running repository instance.

Usage::

    python sample_data/load.py                       # POST to http://localhost:8000
    python sample_data/load.py --base-url http://host:8000
    python sample_data/load.py --direct              # write straight to storage+index

``--direct`` bypasses HTTP and uses the RepositoryService against whatever
``STORAGE_BACKEND`` is configured (defaults to the local fs backend) — handy for
seeding before the server is started.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
# Updated variants re-published after the base set to demonstrate snapshotting:
# each shares an ``id`` with a base artifact, so publishing it archives the
# previous version as a dated snapshot.
UPDATE_DIR = Path(__file__).resolve().parent / "updates"


def _iter_artifacts() -> list[dict]:
    artifacts = []
    for path in sorted(ARTIFACT_DIR.glob("*.json")):
        artifacts.append(json.loads(path.read_text(encoding="utf-8")))
    return artifacts


def _iter_updates() -> list[dict]:
    updates = []
    if UPDATE_DIR.exists():
        for path in sorted(UPDATE_DIR.glob("*.json")):
            updates.append(json.loads(path.read_text(encoding="utf-8")))
    return updates


def _post_http(base_url: str, art: dict) -> dict | None:
    body = json.dumps(art).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/v1/artifacts",
        data=body,
        headers={"Content-Type": "application/ld+json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_via_http(base_url: str) -> int:
    base_url = base_url.rstrip("/")
    ok = 0
    for art in _iter_artifacts():
        try:
            data = _post_http(base_url, art)
            print(f"  [201] {data['partner']:<10} {data['type']:<16} {data['id']}")
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
            data = _post_http(base_url, art)
            created = data.get("version_created")
            note = "snapshot created" if created else "unchanged (no snapshot)"
            print(f"  [upd] {data['partner']:<10} {data['type']:<16} {data['id']}  ({note})")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"  [{exc.code}] {art.get('id')} -> {detail}", file=sys.stderr)
    return ok


def load_direct() -> int:
    # Import lazily so HTTP mode has no app dependencies.
    from app.config import get_settings
    from app.index import FtsIndex
    from app.service import RepositoryService
    from app.storage import build_storage

    settings = get_settings()
    settings.ensure_local_dirs()
    service = RepositoryService(
        settings, build_storage(settings), FtsIndex(settings.index_path)
    )
    ok = 0
    for art in _iter_artifacts():
        resp = service.publish(art)
        print(f"  [ok] {resp.partner:<10} {resp.type:<16} {resp.id}")
        ok += 1
    # Re-publish updated variants to create snapshots of the prior versions.
    for art in _iter_updates():
        resp = service.publish(art)
        note = "snapshot created" if resp.version_created else "unchanged (no snapshot)"
        print(f"  [upd] {resp.partner:<10} {resp.type:<16} {resp.id}  ({note})")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Write directly to storage/index instead of using HTTP.",
    )
    args = parser.parse_args()

    total = len(_iter_artifacts())
    print(f"Loading {total} sample artifact(s)…")
    ok = load_direct() if args.direct else load_via_http(args.base_url)
    print(f"Done: {ok}/{total} loaded.")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
