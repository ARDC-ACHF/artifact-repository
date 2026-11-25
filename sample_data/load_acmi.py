#!/usr/bin/env python3
"""Fetch an ACMI work or creator as Linked Art JSON-LD and publish it to the repository.

Usage::

    python sample_data/load_acmi.py
    python sample_data/load_acmi.py https://api.acmi.net.au/works/75517/
    python sample_data/load_acmi.py --work-id 125569 --base-url http://host:8000
    python sample_data/load_acmi.py --creator-id 123
    python sample_data/load_acmi.py --direct

HTTP mode reads API_AUTH_USERNAME and API_AUTH_PASSWORD from the environment.
Credentials are sent only to the repository, not to the ACMI Public API.
For --direct, stop the server first and use --data-dir to select its data.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TIMEOUT = 30


def _record_url(record: str | int, kind: str) -> str:
    """Normalise an ID or ACMI URI to the selected JSON-LD endpoint."""
    value = str(record).strip()
    if re.fullmatch(r"[0-9]+", value):
        record_id = int(value)
    else:
        parsed = urllib.parse.urlsplit(value)
        match = re.fullmatch(rf"/{kind}s/([0-9]+)/?", parsed.path)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.netloc.lower() != "api.acmi.net.au"
            or match is None
        ):
            raise ValueError(
                f"Expected a positive {kind} ID or an ACMI URI such as "
                f"https://api.acmi.net.au/{kind}s/123/."
            )
        record_id = int(match[1])
    if record_id <= 0:
        raise ValueError(f"{kind.capitalize()} ID must be a positive integer.")
    # Discard query strings and fragments so they cannot override JSON-LD.
    return f"https://api.acmi.net.au/{kind}s/{record_id}/?format=jsonld"


def work_url(work: str | int) -> str:
    """Normalise a work ID or ACMI work URI to the JSON-LD API endpoint."""
    return _record_url(work, "work")


def creator_url(creator: str | int) -> str:
    """Normalise a creator ID or ACMI creator URI to the JSON-LD endpoint."""
    return _record_url(creator, "creator")


def _fetch_record(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/ld+json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        artifact = json.load(response)
    if not isinstance(artifact, dict):
        raise ValueError("ACMI returned a JSON value that is not an object.")
    return artifact


def fetch_work(work: str | int) -> dict:
    return _fetch_record(work_url(work))


def fetch_creator(creator: str | int) -> dict:
    return _fetch_record(creator_url(creator))


def _auth_header() -> str:
    username = os.environ.get("API_AUTH_USERNAME", "")
    password = os.environ.get("API_AUTH_PASSWORD", "")
    if not username.strip() or ":" in username or not password.strip():
        raise ValueError(
            "Set API_AUTH_USERNAME (without ':') and API_AUTH_PASSWORD "
            "to the server's credentials."
        )
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def publish_http(artifact: dict, base_url: str) -> dict:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/artifacts",
        data=json.dumps(artifact, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/ld+json"},
        method="POST",
    )
    request.add_unredirected_header("Authorization", _auth_header())
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def publish_direct(artifact: dict, data_dir: Path = Path("data")) -> dict:
    # Support running this file by path without installing the app package.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.index import FtsIndex
    from app.service import RepositoryService, ValidationFailed
    from app.storage.fs_store import FilesystemStore

    index = FtsIndex(data_dir / "index.sqlite3")
    try:
        service = RepositoryService(FilesystemStore(data_dir / "artifacts"), index)
        return service.publish(artifact).model_dump()
    except ValidationFailed as exc:
        raise ValueError(exc.result.model_dump_json()) from exc
    finally:
        index.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", nargs="?", help="ACMI work ID or work/creator URI (default: work 125569).")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--work-id", help="ACMI work ID or full work URI.")
    selection.add_argument("--creator-id", help="ACMI creator ID or full creator URI.")
    selection.add_argument("--uri", help="ACMI work/creator URI or work ID.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--direct", action="store_true", help="Write directly to filesystem storage/index; stop the server first.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Data directory for --direct (default: ./data).")
    args = parser.parse_args(argv)
    options = (args.work_id, args.creator_id, args.uri)
    if args.record is not None and any(value is not None for value in options):
        parser.error("Supply either a positional record or --work-id/--creator-id/--uri, not both.")
    record = next((value for value in (args.record, *options) if value is not None), "125569")
    kind = "work"
    try:
        if args.creator_id is not None or (
            args.work_id is None and urllib.parse.urlsplit(record).path.startswith("/creators/")
        ):
            kind = "creator"
        url = creator_url(record) if kind == "creator" else work_url(record)
    except ValueError as exc:
        parser.error(str(exc))

    stage = "configure repository authentication"
    try:
        if not args.direct:
            _auth_header()
        stage = f"fetch ACMI {kind}"
        print(f"Fetching {url}…")
        artifact = fetch_creator(url) if kind == "creator" else fetch_work(url)
        stage = f"publish ACMI {kind}"
        result = (
            publish_direct(artifact, args.data_dir)
            if args.direct
            else publish_http(artifact, args.base_url)
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Could not {stage}: HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"Could not {stage}: {exc}", file=sys.stderr)
        return 1

    note = "new version stored" if result["version_created"] else "unchanged (no new version)"
    print(f"  [ok] {result['partner']:<10} {result['type']:<16} {result['id']} ({note})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
