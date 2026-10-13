#!/usr/bin/env python3
"""Fetch an ACMI work as Linked Art JSON-LD and publish it to the repository.

Usage::

    python sample_data/load_acmi.py
    python sample_data/load_acmi.py https://api.acmi.net.au/works/75517/
    python sample_data/load_acmi.py --work-id 125569 --base-url http://host:8000
    python sample_data/load_acmi.py --direct
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TIMEOUT = 30


def work_url(work: str | int) -> str:
    """Normalise a work ID or ACMI work URI to the JSON-LD API endpoint."""
    value = str(work).strip()
    if re.fullmatch(r"[0-9]+", value):
        work_id = int(value)
    else:
        parsed = urllib.parse.urlsplit(value)
        match = re.fullmatch(r"/works/([0-9]+)/?", parsed.path)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.netloc.lower() != "api.acmi.net.au"
            or match is None
        ):
            raise ValueError("Expected a positive work ID or an ACMI URI such as https://api.acmi.net.au/works/75517/.")
        work_id = int(match[1])
    if work_id <= 0:
        raise ValueError("Work ID must be a positive integer.")
    # Build the canonical endpoint so existing format parameters and fragments
    # cannot override JSON-LD or become part of the record's stored identity.
    return f"https://api.acmi.net.au/works/{work_id}/?format=jsonld"


def fetch_work(work: str | int) -> dict:
    url = work_url(work)
    request = urllib.request.Request(url, headers={"Accept": "application/ld+json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        artifact = json.load(response)
    if not isinstance(artifact, dict):
        raise ValueError("ACMI returned a JSON value that is not an object.")
    return artifact


def publish_http(artifact: dict, base_url: str) -> dict:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/artifacts",
        data=json.dumps(artifact, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/ld+json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def publish_direct(artifact: dict) -> dict:
    # Support running this file by path without installing the app package.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.config import get_settings
    from app.index import FtsIndex
    from app.service import RepositoryService, ValidationFailed
    from app.storage import build_storage

    settings = get_settings()
    settings.ensure_local_dirs()
    service = RepositoryService(
        settings, build_storage(settings), FtsIndex(settings.index_path)
    )
    try:
        return service.publish(artifact).model_dump()
    except ValidationFailed as exc:
        raise ValueError(exc.result.model_dump_json()) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", nargs="?", help="ACMI work ID or full URI (default: 125569).")
    parser.add_argument("--work-id", "--uri", dest="work_option", help="ACMI work ID or full URI, instead of the positional argument.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--direct", action="store_true", help="Write directly to configured storage/index.")
    args = parser.parse_args(argv)
    if args.work is not None and args.work_option is not None:
        parser.error("Supply either a positional work or --work-id/--uri, not both.")
    work = args.work if args.work is not None else args.work_option
    try:
        url = work_url(work if work is not None else 125569)
    except ValueError as exc:
        parser.error(str(exc))

    stage = "fetch ACMI work"
    try:
        print(f"Fetching {url}…")
        artifact = fetch_work(url)
        stage = "publish ACMI work"
        result = (
            publish_direct(artifact)
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
