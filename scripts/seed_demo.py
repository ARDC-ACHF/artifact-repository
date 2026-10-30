"""Seed the curated AusStage + DAAO demo records into a local data directory.

Usage::

    python scripts/seed_demo.py --data-dir demo_data

Records are validated first (nothing is published if any record is invalid),
then published through :class:`RepositoryService` with the same storage/index
wiring as the API (``<data-dir>/artifacts`` + ``<data-dir>/index.sqlite3``).
Re-running is safe: unchanged records are idempotent no-ops.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.index import FtsIndex  # noqa: E402
from app.models import PublishResponse  # noqa: E402
from app.service import RepositoryService  # noqa: E402
from app.storage.fs_store import FilesystemStore  # noqa: E402
from app.validation.validator import LinkedArtValidator  # noqa: E402

DEFAULT_SOURCE = REPO_ROOT / "sample_data" / "demo"
# Referenced entities first so places and people exist before what links to them.
_TYPE_ORDER = {"Place": 0, "Person": 1, "Group": 2}


def load_records(source: Path = DEFAULT_SOURCE) -> list[tuple[Path, dict]]:
    """Load every ``*.json`` record in ``source``, sorted places-first."""
    records = [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(Path(source).glob("*.json"))
    ]
    return sorted(records, key=lambda item: (_TYPE_ORDER.get(item[1].get("type"), 9), item[0].name))


def seed(data_dir: Path, source: Path = DEFAULT_SOURCE) -> list[PublishResponse]:
    """Validate then publish all demo records into ``data_dir``."""
    records = load_records(source)
    if not records:
        raise SystemExit(f"No demo records found in {source}")
    validator = LinkedArtValidator()
    invalid = [
        f"{path.name}: {[e.message for e in result.errors]}"
        for path, payload in records
        if not (result := validator.validate(payload)).valid
    ]
    if invalid:
        raise SystemExit("Invalid demo records, nothing published:\n  " + "\n  ".join(invalid))

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    index = FtsIndex(data_dir / "index.sqlite3")
    try:
        service = RepositoryService(FilesystemStore(data_dir / "artifacts"), index, validator)
        return [service.publish(payload) for _, payload in records]
    finally:
        index.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "demo_data",
                        help="repository data directory (default: demo_data)")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help="directory of demo JSON-LD records (default: sample_data/demo)")
    args = parser.parse_args(argv)

    results = seed(args.data_dir, args.source)
    created = sum(r.version_created for r in results)
    by_group = Counter((r.partner, r.type) for r in results)
    print(f"Seeded {len(results)} records into {args.data_dir} "
          f"({created} new versions, {len(results) - created} unchanged)")
    for (partner, type_), count in sorted(by_group.items()):
        print(f"  {partner:<10} {type_:<16} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
