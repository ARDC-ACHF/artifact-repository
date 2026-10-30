"""Seed the curated AusStage + DAAO demo records into a local data directory.

Usage::

    python scripts/seed_demo.py --data-dir demo_data [--reset]

Records are validated first (nothing is published if any record is invalid),
then published through :class:`RepositoryService` with the same storage/index
wiring as the API (``<data-dir>/artifacts`` + ``<data-dir>/index.sqlite3``).

Curatorial revisions live in ``<source>/revisions/<base-name>.v<N>.json``
(full records sharing the base record's ``id``, numbered from 2). They are
published after all base records, in version order, so the newest revision is
current. While seeding, the service clock is replaced by a fixed demo clock so
version dates read as a plausible 2024–2025 history; the live API's clock is
never touched.

Re-running is safe: records already at their latest demo version are
idempotent no-ops. ``--reset`` deletes the data directory's artifacts and index
first, so backdated versions never land behind versions stamped today.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import app.service as service_module  # noqa: E402
from app.index import FtsIndex  # noqa: E402
from app.models import PublishResponse  # noqa: E402
from app.service import RepositoryService  # noqa: E402
from app.storage.fs_store import FilesystemStore  # noqa: E402
from app.validation.validator import LinkedArtValidator  # noqa: E402

DEFAULT_SOURCE = REPO_ROOT / "sample_data" / "demo"
REVISIONS_DIRNAME = "revisions"
# Referenced entities first so places and people exist before what links to them.
_TYPE_ORDER = {"Place": 0, "Person": 1, "Group": 2}
_REVISION_NAME = re.compile(r"^(?P<base>.+)\.v(?P<version>\d+)\.json$")

# Demo clock: base records on 2024-03-14 (one minute apart, in publish order);
# revision N on its own day, one minute apart per record.
_STAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
BASE_DATE = datetime(2024, 3, 14, 9, 0)
REVISION_DATES = {2: datetime(2024, 8, 21, 10, 0), 3: datetime(2025, 2, 10, 14, 0)}


class SeedResult(list):
    """Base-record :class:`PublishResponse` list plus revisions and warnings."""

    def __init__(self, results=(), revisions=(), warnings=()):
        super().__init__(results)
        self.revisions: list[PublishResponse] = list(revisions)
        self.warnings: list[str] = list(warnings)


def load_records(source: Path = DEFAULT_SOURCE) -> list[tuple[Path, dict]]:
    """Load every top-level ``*.json`` record in ``source``, sorted places-first."""
    records = [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(Path(source).glob("*.json"))
    ]
    return sorted(records, key=lambda item: (_TYPE_ORDER.get(item[1].get("type"), 9), item[0].name))


def load_revisions(source: Path = DEFAULT_SOURCE) -> dict[str, list[tuple[int, Path, dict]]]:
    """Load ``<source>/revisions/*.v<N>.json`` grouped by base file name, in version order."""
    grouped: dict[str, list[tuple[int, Path, dict]]] = {}
    for path in sorted((Path(source) / REVISIONS_DIRNAME).glob("*.json")):
        match = _REVISION_NAME.match(path.name)
        if not match:
            raise SystemExit(f"Revision file name must be <base-name>.v<N>.json: {path.name}")
        grouped.setdefault(f"{match['base']}.json", []).append(
            (int(match["version"]), path, json.loads(path.read_text(encoding="utf-8")))
        )
    return {base: sorted(items, key=lambda item: item[0]) for base, items in sorted(grouped.items())}


def _check(records, revisions, validator) -> None:
    problems = [
        f"{path.name}: {[e.message for e in result.errors]}"
        for path, payload in [*records, *((p, r) for revs in revisions.values() for _, p, r in revs)]
        if not (result := validator.validate(payload)).valid
    ]
    by_name = {path.name: payload for path, payload in records}
    for base, revs in revisions.items():
        if base not in by_name:
            problems.append(f"{revs[0][1].name}: no base record {base}")
            continue
        versions = [version for version, _, _ in revs]
        if versions != list(range(2, len(revs) + 2)):
            problems.append(f"{base}: revisions must be numbered v2, v3, … without gaps (got {versions})")
        problems += [
            f"{path.name}: id {payload.get('id')!r} does not match base id {by_name[base].get('id')!r}"
            for _, path, payload in revs if payload.get("id") != by_name[base].get("id")
        ]
        problems += [f"{path.name}: no demo date for v{version}" for version, path, _ in revs
                     if version not in REVISION_DATES]
    if problems:
        raise SystemExit("Invalid demo records, nothing published:\n  " + "\n  ".join(problems))


def reset_data_dir(data_dir: Path) -> None:
    """Delete only the repository artifacts folder and SQLite index in ``data_dir``."""
    data_dir = Path(data_dir)
    shutil.rmtree(data_dir / "artifacts", ignore_errors=True)
    for suffix in ("", "-wal", "-shm", "-journal"):
        (data_dir / f"index.sqlite3{suffix}").unlink(missing_ok=True)


def _stamp(moment: datetime) -> str:
    return moment.strftime(_STAMP_FORMAT)


def seed(data_dir: Path, source: Path = DEFAULT_SOURCE, *, reset: bool = False) -> SeedResult:
    """Validate then publish all demo records (and their revisions) into ``data_dir``."""
    records = load_records(source)
    if not records:
        raise SystemExit(f"No demo records found in {source}")
    revisions = load_revisions(source)
    validator = LinkedArtValidator()
    _check(records, revisions, validator)

    data_dir = Path(data_dir)
    if reset:
        reset_data_dir(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    clock = {"now": ""}
    warnings: list[str] = []
    results: list[PublishResponse] = []
    applied: list[PublishResponse] = []
    index = FtsIndex(data_dir / "index.sqlite3")
    try:
        service = RepositoryService(FilesystemStore(data_dir / "artifacts"), index, validator)

        def publish_at(moment: datetime, name: str, payload: dict) -> PublishResponse:
            clock["now"] = _stamp(moment)
            current = service.get_current(payload["id"])
            if (current is not None and not RepositoryService._same_content(current, payload)
                    and (current.published_at or "") > clock["now"]):
                warnings.append(
                    f"{name}: new version dated {clock['now']} lands behind the existing current "
                    f"version {current.published_at}; re-run with --reset for a clean history")
            return service.publish(payload)

        with mock.patch.object(service_module, "_now_published_at", lambda: clock["now"]):
            pending: list[tuple[int, int, Path, dict]] = []
            for position, (path, payload) in enumerate(records):
                revs = revisions.get(path.name, [])
                chain = [payload, *(rev for _, _, rev in revs)]
                current = service.get_current(payload["id"])
                # Resume after the newest demo version already stored (idempotent re-seed).
                done = next((i for i in reversed(range(len(chain)))
                             if current is not None and RepositoryService._same_content(current, chain[i])), 0)
                results.append(publish_at(BASE_DATE + timedelta(minutes=position), path.name, chain[done]))
                pending += [(version, position, rev_path, rev) for version, rev_path, rev in revs[done:]]
            for version, position, rev_path, payload in sorted(pending, key=lambda item: item[:2]):
                applied.append(publish_at(REVISION_DATES[version] + timedelta(minutes=position),
                                          rev_path.name, payload))
    finally:
        index.close()
    return SeedResult(results, applied, warnings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "demo_data",
                        help="repository data directory (default: demo_data)")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help="directory of demo JSON-LD records (default: sample_data/demo)")
    parser.add_argument("--reset", action="store_true",
                        help="delete <data-dir>/artifacts and index.sqlite3 before seeding")
    args = parser.parse_args(argv)

    results = seed(args.data_dir, args.source, reset=args.reset)
    created = sum(r.version_created for r in results)
    print(f"Seeded {len(results)} records into {args.data_dir} "
          f"({created} new versions, {len(results) - created} unchanged)")
    revised = {r.id for r in results.revisions}
    print(f"Applied {len(results.revisions)} revisions to {len(revised)} records")
    by_group = Counter((r.partner, r.type) for r in results)
    for (partner, type_), count in sorted(by_group.items()):
        print(f"  {partner:<10} {type_:<16} {count}")
    for warning in results.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
