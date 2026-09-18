# Linked Art Interoperability Repository

A foundation for a shared repository of humanities data expressed as
[Linked Art](https://linked.art/) JSON-LD. The intended service will let partner
platforms publish artifacts for cross-domain discovery.

## Current scope

The application provides basic offline Linked Art profile validation, a
liveness endpoint, interactive API documentation and automated tests.
It does not store or search artifacts. No credentials, external services or
runtime data directories are required.

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
app/main.py           Application factory, health and validation endpoints
app/models.py         Validation response contracts
app/validation/      Profile checks and bundled offline context
tests/test_health.py  Startup, health and documentation smoke tests
tests/test_validation.py  Validator and API contract tests
tests/fixtures/       Representative prototype documents from three domains
requirements.txt     Runtime dependencies
requirements-dev.txt Test dependencies, including runtime requirements
constraints.txt      Pinned direct and transitive dependency versions
.github/workflows/ci.yml  Tests for PRs targeting master/project-foundation and pushes to master
```

Both installation paths use `constraints.txt` to keep dependency versions
consistent. When updating dependencies, update the pins together and rerun
`python -m pip check` and `python -m pytest` in a fresh virtual environment.
Virtual environments, Python/test caches, local environment files and future
runtime `data/` are excluded from Git.

## Basic validation

`POST /api/v1/artifacts/validate` accepts a JSON document and never stores it.
Valid input returns HTTP 200 with `{"valid":true,"errors":[]}`. Malformed JSON
and failed validation return HTTP 422 with the same envelope and errors
containing `path`, `code` and `message`.

From the repository root, with the server running:

```bash
curl -i http://localhost:8000/api/v1/artifacts/validate \
  -H 'Content-Type: application/json' \
  --data-binary @tests/fixtures/nga_object_98765.json

curl -i http://localhost:8000/api/v1/artifacts/validate \
  -H 'Content-Type: application/json' \
  -d '{"@context":"https://linked.art/ns/v1/linked-art.json","id":"https://example.org/1","type":"Unknown"}'
```

The second request returns HTTP 422:

```json
{"valid":false,"errors":[{"path":"$.type","code":"unsupported_type","message":"Top-level 'type' is not a supported Linked Art class."}]}
```

### Accepted profile

- The document must be an object with non-empty string `@context`, `id` and `type`.
- `@context` must be exactly `https://linked.art/ns/v1/linked-art.json`.
  Inline contexts, context arrays, alternative URLs and fragments are rejected.
  The same restriction applies to any explicit nested contexts; the bundled
  context's own scoped definitions remain supported.
- `id` must be non-blank. Absolute IRI syntax, uniqueness and resolvability
  are **not** checked yet; relative identifiers may pass.
- Supported top-level types: `HumanMadeObject`, `LinguisticObject`, `Text`,
  `Activity`, `Event`, `Person`, `Group`, `Place`, `Set`, `VisualItem`.
- Structurally valid input must expand as JSON-LD using the local context.
  No remote documents are fetched. See [context attribution](app/validation/context/README.md).

Error codes are `invalid_json` (malformed body), `invalid_type` (wrong JSON
shape or field type), `missing_field` (absent, null, blank or empty-list required
field), `unsupported_type`, `unsupported_context`, and `invalid_jsonld`.
Paths use `$` for the document and `$.field` / `[index]` for fields and entries.
Structural errors are collected before expansion to avoid redundant errors.

These are basic profile checks, **not full Linked Art, CIDOC-CRM or SHACL
conformance**. Unknown properties may be ignored by JSON-LD expansion, and
nested entities are not checked against a domain schema. Authentication,
rate/body-size limits and production hardening are deferred.

`python -m pytest` exercises all supported types, three representative fixtures,
malformed JSON, invalid fields/contexts and the API response contract. Validation
tests block network connections and run in an empty temporary working directory
to check that no storage/index directories are created.

## Planned architecture and follow-up PRs

The planned data flow is partner JSON-LD → validation → storage and search
index → retrieval/search API. Only basic validation is currently included.

1. Local persistence and versioning.
2. Repository API, indexing and cross-domain search.
3. Demo frontend and sample-data walkthrough.
4. Swift storage backend and deployment support.