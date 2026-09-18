# Linked Art Interoperability Repository

A foundation for a shared repository of humanities data expressed as
[Linked Art](https://linked.art/) JSON-LD. The intended service will let partner
platforms publish artifacts for cross-domain discovery.

## Current scope

This initial contribution provides only a runnable FastAPI application, a
liveness endpoint, interactive API documentation and automated smoke tests.
It does not yet validate, store or search artifacts. No credentials, external
services or runtime data directories are required.

## Local quickstart

Use Python 3.11 (the version tested in CI).

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
uvicorn app.main:app --reload
```

On Windows, activate with `.venv\Scripts\activate` instead.
For a runtime-only installation, use `requirements.txt`.

- Health: <http://localhost:8000/health> returns HTTP 200 and `{"status":"ok"}`.
- Interactive API docs: <http://localhost:8000/docs>.
- OpenAPI schema: <http://localhost:8000/openapi.json>.

`/health` indicates application liveness only; it does not check storage or
index readiness. There is no frontend at `/` yet.

## Project layout

```text
app/__init__.py       Package metadata
app/main.py           Application factory and health endpoint
tests/test_health.py  Startup, health and documentation smoke tests
requirements.txt     Runtime dependencies
requirements-dev.txt Test dependencies, including runtime requirements
constraints.txt      Pinned direct and transitive dependency versions
.github/workflows/ci.yml  Tests for PRs targeting master and pushes to master
```

Both installation paths use `constraints.txt` to keep dependency versions
consistent. When updating dependencies, update the pins together and rerun
`python -m pip check` and `python -m pytest` in a fresh virtual environment.
Virtual environments, Python/test caches, local environment files and future
runtime `data/` are excluded from Git.

## Planned architecture and follow-up PRs

The planned data flow is partner JSON-LD → validation → storage and search
index → retrieval/search API. None of these repository capabilities are
included in this foundation.

1. Linked Art profile validation and representative fixtures.
2. Local persistence and versioning.
3. Repository API, indexing and cross-domain search.
4. Demo frontend and sample-data walkthrough.
5. Swift storage backend and deployment support.
