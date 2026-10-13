# Reviewer Guide

This PR contains the whole artifact repository service. It is easiest to review
feature by feature, in the order below: each feature builds on the previous ones.
Commits follow the same order, so `git log --reverse` / per-commit view also works.

## Architecture at a glance

```
HTTP (app/main.py, app/api.py)  ->  auth (app/auth.py)
            |
            v
RepositoryService (app/service.py)
   |            |                 |
   v            v                 v
validation/   storage/          index/fts_index.py
              (base -> fs | swift)   (+ extract.py, partners.py)
```

Routes are thin and delegate to `RepositoryService`; storage is behind an
interface (`app/storage/base.py`) with filesystem and Swift backends.

## Running it

```
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt -c constraints.txt
pytest
```

## Review order

### 1. Project foundation (`e37a26b`, `42d8e18`)
App skeleton, health endpoint, dependencies, CI.
- Key files: `app/main.py`, `requirements.txt`, `constraints.txt`, `.github/workflows/ci.yml`
- Tests: `tests/test_health.py`
- Quick skim.

### 2. Validation and errors (`475879d`)
Linked Art JSON-LD validation with a locally loaded context and a supported-type allowlist; error responses.
- Key files: `app/validation/validator.py`, `app/validation/context_loader.py`, `app/validation/supported_types.py`, `app/models.py`
- Tests: `tests/test_validation.py`, fixtures in `tests/fixtures/`
- **Skip:** `app/validation/context/linked-art.json` (vendored, ~3.2k lines; provenance in `app/validation/context/README.md`).

### 3. Storage and versioning (`637f6bf`)
Storage interface and versioned artifact layout; filesystem and Swift backends.
- Key files: `app/storage/base.py` (start here), `app/storage/fs_store.py`, `docs/storage.md`
- Secondary: `app/storage/swift_store.py` (optional backend, `requirements-swift.txt`)
- Tests: `tests/test_storage.py`

### 4. Publication, retrieval and search (`c274df8`) — largest step, most review time
Publishing (dedup, version creation), reading current/raw/versioned artifacts, listing, and full-text search.
- Key files: `app/service.py` (`publish`, `_publish`, `_same_content`, `get_*`, `list`, `search`, `reindex`), `app/api.py`, `app/index/fts_index.py`
- Supporting: `app/extract.py` (metadata extraction for the index), `app/partners.py` (partner / IRI mapping), `app/models.py`
- Docs: `docs/repository-api.md`
- Tests: `tests/test_service.py`, `tests/test_repository_api.py`, `tests/test_index.py`

### 5. Basic auth (`4258a76`)
Dev-only basic auth, structured so other methods can be added later.
- Key files: `app/auth.py`, wiring in `app/main.py`
- Tests: `tests/test_auth.py`
- Note: production auth is out of scope.

### 6. Artifact deletion (`619266f`)
Deleting artifacts and individual versions, keeping the index consistent.
- Key files: `app/service.py` (`delete`, `delete_version`, `_repair_deletion_index`), `app/api.py`
- Docs: deletion section of `docs/repository-api.md`
- Tests: `tests/test_deletion.py`

### 7. Tooling (`706a8dd`, `a819cc1`)
Python 3.13 upgrade and `.gitignore` hardening; no behaviour change.
- Files: `.python-version`, `.github/workflows/ci.yml`, `constraints.txt`, `README.md`, `.gitignore`

## Points worth particular attention
- `app/service.py` holds most of the business logic (publish, versioning, deletion, index repair).
- Consistency between storage and the search index on failure (`_index_stored`, `_repair_deletion_index`, `reindex`).

## Out of scope / known gaps
- Swift backend is optional and not exercised against a real Swift service.
- Auth is dev-only basic auth.
- No dedicated docs yet for auth, validation or the index.
