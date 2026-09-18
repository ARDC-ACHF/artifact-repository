# Repository API

Run `uvicorn app.main:app --reload` from the repository root. The default service
uses `data/artifacts/` and `data/index.sqlite3` (ignored by Git). SQLite must have
FTS5 support. Configure `API_AUTH_USERNAME` and `API_AUTH_PASSWORD` before starting;
see [authentication setup](../README.md#api-authentication). Every API endpoint
requires HTTP Basic credentials. Missing credentials return 401; missing server
configuration returns 503. Health and documentation stay public.

## Endpoints

| Method/path | Behaviour |
| --- | --- |
| `POST /api/v1/artifacts` | Validate and publish; 201 for a new version, 200 for unchanged content. |
| `GET /api/v1/artifacts/item?iri=...` | Current JSON-LD, or 404. |
| `GET /api/v1/artifacts/version?iri=...&published_at=...` | Historical JSON-LD, or 404. |
| `GET /api/v1/artifacts/versions?iri=...` | Newest-first history, current flag and version locators; 404 if unknown. |
| `GET /api/v1/artifacts` | Current summaries with optional `partner`, `type`, `limit`, `offset`. |
| `GET /api/v1/search?q=...` | Current full-text matches with repeated `partners`/`types`, `limit`, `offset`. |

Pagination defaults to 50 results, accepts limits 1–200 and nonnegative offsets.
`total` counts all matches before pagination. Search treats whitespace-separated
terms as literal prefixes combined with AND, not raw FTS syntax. Only current
versions are indexed. Partner slugs are inferred from known identifier hosts
(`nga`, `ausstage`, `austlit`); unknown hosts use their first non-`www` label,
and hostless identifiers use `unknown`. This is a discovery heuristic, not a
verified publisher identity. Search text includes labels and nested
`content`, `value` and `label` strings.

Identifiers use query parameters to preserve slashes, percent signs, query
strings and fragments without path-decoding ambiguity. Follow returned
`locator`/`stored_at` links, or use `curl --get --data-urlencode`.

## Verifiable walkthrough

```bash
curl -i --user "$API_AUTH_USERNAME" http://localhost:8000/api/v1/artifacts \
  -H 'Content-Type: application/json' \
  -d '{"@context":"https://linked.art/ns/v1/linked-art.json","id":"https://nga.gov.au/object/review","type":"HumanMadeObject","_label":"Golden landscape"}'

curl --user "$API_AUTH_USERNAME" --get http://localhost:8000/api/v1/artifacts/item \
  --data-urlencode 'iri=https://nga.gov.au/object/review'

curl --user "$API_AUTH_USERNAME" --get http://localhost:8000/api/v1/search \
  --data-urlencode 'q=Golden' --data-urlencode 'partners=nga'
```

Publication returns `id`, `type`, `partner`, `locator`, `stored_at` (a version
HTTP URL, never a backend filesystem path), `published_at`, `version_created`
and `snapshot_of` (the previous version timestamp, or null). `Location` points
to the current artifact. Repeating the first request returns 200 with
`version_created: false` and the same timestamp. JSON object key order is ignored;
array order and values remain significant. Stored JSON is serialized from the
parsed document, not the original request's whitespace.

Change the label to `Silver portrait` and publish again: expect 201 and a new
canonical UTC microsecond timestamp. The first version remains accessible via
its `stored_at` URL; searching `Golden` no longer returns this artifact.

```bash
curl --user "$API_AUTH_USERNAME" --get http://localhost:8000/api/v1/artifacts/versions \
  --data-urlencode 'iri=https://nga.gov.au/object/review'
```

Invalid publication returns the same 422 `{valid, errors}` envelope as the
validation endpoint and writes no artifact. Invalid query parameters return
FastAPI's 422 `detail` response. Retrieval returns `application/ld+json`.

## Injection and recovery

`create_app(data_dir=Path(...))` selects a local data directory.
`create_app(service=RepositoryService(storage, index))` accepts a filesystem or
Swift backend plus `FtsIndex`; callers own and close an injected index. The
default application's lifespan closes its own index. Health and validation do
not open either backend. Swift credentials/backend selection are not exposed as
environment settings in this slice.

Storage is authoritative. The index is a persistent, rebuildable projection,
not a transaction spanning SQLite and storage. On an indexing failure the
service attempts to restore the previous pointer and remove the new snapshot.
Backend failures, process crashes or failed rollback can still require recovery.
An unchanged re-publication refreshes the index without creating a snapshot.
Direct storage writes are not automatically indexed; to rebuild, stop writers
and run from the repository root:

```python
from pathlib import Path
from app.index import FtsIndex
from app.service import RepositoryService
from app.storage.fs_store import FilesystemStore

index = FtsIndex(Path("data/index.sqlite3"))
try:
    service = RepositoryService(FilesystemStore(Path("data/artifacts")), index)
    print(service.reindex())
finally:
    index.close()
```

Reindexing is explicit, not performed on every startup. Run one application
process/service writer only; its publication lock does not coordinate multiple
workers, hosts or direct storage clients. There is no distributed transaction,
fine-grained authorization, full schema validation or production availability guarantee.
Live Swift verification remains separate from the offline tests.

## Tests

`python -m pytest` covers publication/retry/update/history, locators, filtering,
pagination, restart persistence, timestamp collisions, failure rollback and
reindexing, alongside the existing validator and shared storage contracts.
Repository API tests use real temporary filesystem storage and SQLite with
network access blocked. CI includes PRs targeting `local-persistence-and-versioning`.