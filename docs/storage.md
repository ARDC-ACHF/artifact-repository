# Versioned storage

This slice ports filesystem persistence and OpenStack Swift storage together.
Both implement `StorageBackend`; neither is connected to the HTTP application
yet. No indexing, metadata extraction, publication endpoint or authentication
configuration is introduced.

## Contract

- `put(iri, body, partner=..., type=..., label=..., published_at=...)` stores exact
  bytes and metadata, then advances the current pointer. Its return value is a
  backend locator, not an HTTP API URL.
- Identifiers must be non-blank strings, preserved verbatim in metadata. Object
  keys are SHA-256 hashes, including for short identifiers, avoiding unsafe paths.
- Callers provide UTC version timestamps in exactly
  `YYYY-MM-DDTHH:MM:SS.ffffffZ` format. History is newest-first by timestamp;
  current means the last successful pointer update, not the largest timestamp.
- A snapshot cannot be overwritten. Repeating the same timestamp, bytes and
  metadata is safe and points to that snapshot; differing content or metadata
  raises `VersionConflictError`. Identical content at a **new timestamp** creates
  another snapshot. Content-based publication deduplication is deferred.
- `get` returns current content; `get_version` retrieves a snapshot. Missing
  artifacts return `None`; missing histories return `[]`.
- `list` returns current artifact metadata. `list_versions` includes retained
  snapshots and marks the current one.
- `restore_pointer(iri, timestamp)` requires an existing snapshot;
  `restore_pointer(iri, None)` unpublishes without deleting history. Missing
  pointers never silently expose retained snapshots.
- `delete_version` rejects deletion of the current snapshot. Restore or clear
  its pointer first. `delete` removes the pointer and all snapshots; repeated
  deletion is safe.
- Invalid identifiers/timestamps raise `ValueError`; filesystem and Swift
  operational errors propagate. Only Swift HTTP 404 means an absent object.
  Constructors create the directory/container and surface initialization errors.

## Filesystem example

From the repository root after installing `requirements.txt`:

```bash
python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from app.storage.fs_store import FilesystemStore

with TemporaryDirectory() as directory:
    store = FilesystemStore(Path(directory))
    iri = "https://example.org/object/1"
    first = "2026-09-18T01:00:00.000000Z"
    second = "2026-09-18T02:00:00.000000Z"
    for timestamp, body in [(first, b'{"label":"first"}'),
                            (second, b'{"label":"second"}')]:
        store.put(iri, body, partner="example", type="HumanMadeObject",
                  published_at=timestamp)
    assert store.get(iri).body == b'{"label":"second"}'
    assert store.get_version(iri, first).body == b'{"label":"first"}'
    assert len(store.list_versions(iri)) == 2
    print(store.list_versions(iri))
PY
```

For persistence between runs, use `FilesystemStore(Path("data/artifacts"))`.
Filesystem snapshots contain bytes encoded as base64 with metadata in a single
JSON record. Complete records are installed without replacing existing versions;
current pointers are atomically replaced. This is **not compatible with the
prototype's old file layout**; no runtime data migration is included.

## Swift example (optional live verification)

```bash
python -m pip install -r requirements.txt -r requirements-swift.txt
```

Supply `OS_STORAGE_URL` (account storage endpoint), `OS_AUTH_TOKEN` (an existing,
short-lived token) and `SWIFT_CONTAINER` (a dedicated test container) in your
environment. Do not put credentials in source control. This example uses a
pre-authenticated connection; Keystone password/application-credential setup
and token renewal are outside this slice.

```bash
python - <<'PY'
import os
from uuid import uuid4
from swiftclient.client import Connection
from app.storage.swift_store import SwiftStore

connection = Connection(preauthurl=os.environ["OS_STORAGE_URL"],
                        preauthtoken=os.environ["OS_AUTH_TOKEN"])
store = SwiftStore(connection, os.environ["SWIFT_CONTAINER"])
iri = "https://example.org/storage-smoke/" + str(uuid4())
first = "2026-09-18T01:00:00.000000Z"
second = "2026-09-18T02:00:00.000000Z"
try:
    for timestamp, body in [(first, b"first"), (second, b"second")]:
        store.put(iri, body, partner="test", type="Person", label="作品",
                  published_at=timestamp)
    assert store.get(iri).body == b"second"
    assert store.get_version(iri, first).body == b"first"
    assert store.get(iri).label == "作品"
    assert len(store.list_versions(iri)) == 2
    store.restore_pointer(iri, first)
    assert store.get(iri).body == b"first"
    print("Swift smoke test passed")
finally:
    store.delete(iri)
    connection.close()
PY
```

This writes/deletes only the randomly named test artifact, but may create the
specified container (which it leaves in place). It requires read/write/list/delete
permissions. Swift version objects hold raw bytes and percent-encoded metadata
headers; pointer objects identify current versions. Conditional object creation
(`If-None-Match: *`) prevents overwriting a snapshot.

## Verification and limitations

Run `python -m pytest tests/test_storage.py` for the shared contract. Swift tests
use an in-memory connection implementing object operations and HTTP failures;
they do **not** establish live Swift, authentication or deployment compatibility.
Run the live example against your target deployment before making those claims.
The existing validation tests still check that application startup/validation
does not initialize storage or access the network.

This is an incremental **single-writer** storage layer, not a transactional
publication service. Writes to a snapshot and its pointer are separate; a failed
pointer update may leave a retained, non-current snapshot, which can be retried
or explicitly deleted. Concurrent pointer updates/deletions, distributed locking,
crash recovery, filesystem power-loss durability, Swift listing consistency,
large-scale pagination and service limits (including metadata size) are not
solved here. Listings materialize all results. `health()` is a basic backend
check, not a full read/write probe, and is not wired to `/health`. Unlike data
operations, Swift `health()` reports client failures as `ok: false` with an
HTTP status rather than exposing exception text that might contain credentials.