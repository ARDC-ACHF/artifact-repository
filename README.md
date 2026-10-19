# Linked Art Interoperability Repository

A foundation for a shared repository of humanities data expressed as
[Linked Art](https://linked.art/) JSON-LD. The intended service will let partner
platforms publish artifacts for cross-domain discovery.

## Current scope

The application provides offline Linked Art profile validation, versioned
publication, current/historical retrieval, listing and filtered full-text search.
Authenticated DELETE endpoints remove individual snapshots or entire artifacts;
deleting the current snapshot promotes the newest remaining snapshot. See
[deletion behavior and examples](docs/repository-api.md#permanent-deletion).
Filesystem storage and a SQLite FTS5 index are initialized lazily on the first
repository request; health, documentation and validation remain storage-free.
API access requires a configured shared username/password; tests supply their
own credentials and require no external services.
Swift storage can be injected through the Python application factory; deployment
and environment-based backend configuration are outside this PR.

## Local quickstart

Use Python 3.11 (the version tested in CI).

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
export API_AUTH_USERNAME=reviewer
# Supply API_AUTH_PASSWORD securely in the environment before starting.
uvicorn app.main:app --reload
```

On Windows, activate with `.venv\Scripts\activate` instead.
For a runtime-only installation, use `requirements.txt`.

On macOS/Linux, `make install-dev` creates `.venv` and installs development
dependencies; `make install` installs runtime dependencies only. After exporting
the authentication variables above, use `make start` to run with automatic reload,
and Ctrl-C or `make stop` from another terminal to stop. Override defaults with,
for example, `make start PORT=8001`. Use `make test` for tests and `make help`
for all commands.

`make clean` removes caches, coverage reports and build output, preserving the
virtual environment and data. `make delete-db` stops the make-managed servers and
deletes `data/index.sqlite3` and its SQLite sidecar files. Stop any independently
launched servers first. Artifact snapshots are preserved, but existing artifacts
need reindexing via `RepositoryService.reindex()` to appear in search again.
The database is currently tracked in Git, so deleting it also appears as a Git change.

With Docker and Docker Compose installed, use `make docker-up` to build the image
and start the app in the background, waiting for its health check. It serves
<http://127.0.0.1:8000>; `make docker-up PORT=8001` changes the host port.
Export `API_AUTH_USERNAME` and `API_AUTH_PASSWORD` first, or set them in an
untracked `.env` file for Compose. API access stays disabled without credentials.
Use `make docker-logs` to follow logs and `make docker-ps` to view status.

Run `make docker-test` to build a test image with development dependencies and
run pytest in a disposable container. It has no network access, host data mounts,
or application credentials. The container is removed even if tests fail, and
the command reports test failures. To select tests, use
`make docker-test TEST_ARGS='-q tests/test_health.py'`; `make test` also accepts
`TEST_ARGS`. The default application image excludes test dependencies.

`make stop` stops the local development server and runs Compose teardown,
removing this project's containers and network. `make docker-down` does only
the Compose teardown; `make stop-local` stops only the local server. Docker
must be running for Compose teardown to succeed. The `./data` bind mount keeps
data on the host across container removal; built images are also retained.
Local and container servers share this data, so stop one before starting the other.

- Health: <http://localhost:8000/health> returns HTTP 200 and `{"status":"ok"}`.
- Interactive API docs: <http://localhost:8000/docs>.
- OpenAPI schema: <http://localhost:8000/openapi.json>.

`/health` indicates application liveness only; it does not check storage or
index readiness. There is no frontend at `/` yet.

## API authentication

Set `API_AUTH_USERNAME` and `API_AUTH_PASSWORD` before starting the application.
Use a long, randomly generated password; never commit it. Environment values are
read when the application is created; restart to rotate credentials. `.env` files
are not automatically loaded. The username must not contain a colon.

All `/api` and `/api/...` requests require HTTP Basic authentication, including
validation and read-only requests. Missing/invalid credentials return 401 with
a `WWW-Authenticate` challenge. Missing/blank configuration returns 503 and
never enables anonymous access. `/health`, `/docs`, `/redoc` and `/openapi.json`
remain public; health reports liveness, not authentication readiness.

In `/docs`, select **Authorize** and enter the configured username/password.
For curl, use `--user "$API_AUTH_USERNAME"` to prompt for the password, as below.
**Use HTTPS outside localhost:** Basic credentials are encoded, not encrypted.
Do not log Authorization headers or expose this development server directly.

`app/auth.py` separates the ASGI middleware from authentication providers.
`create_app(auth_providers=(... ,))` can inject multiple providers, each with a
unique authorization scheme, async `authenticate(credentials)` method, challenge
and OpenAPI security definition. The middleware selects only the supplied
scheme, rejects duplicate Authorization headers and exposes the verified
`Principal` as `request.state.principal`. An empty provider tuple denies access.
API routes must stay under `/api/` to inherit this boundary.

Only Basic is implemented. A future Bearer provider can validate OAuth/OIDC
access tokens (signature, issuer, audience and expiry) without changing routes.
Login flows, permissions/scopes, individual accounts, rate limiting and browser
CSRF protection are not implemented. All holders of the shared credential have
equal read/write access; this is not a complete production security solution.

## Project layout

```text
app/__init__.py       Package metadata
app/main.py           Application factory, health and validation endpoints
app/api.py            Publication, retrieval, listing and search endpoints
app/auth.py           Authentication middleware and pluggable Basic provider
app/service.py        Validation/storage/index orchestration and reindexing
app/index/            SQLite FTS5 search projection
app/extract.py        Label and searchable-text extraction
app/partners.py       Identifier host to partner mapping
app/models.py         Validation and repository response contracts
app/validation/      Profile checks and bundled offline context
app/storage/         Shared contract, filesystem and Swift versioned storage
docs/storage.md      Storage contract and runnable backend examples
tests/test_health.py  Startup, health and documentation smoke tests
tests/test_validation.py  Validator and API contract tests
tests/test_storage.py  Shared offline backend contract and failure tests
tests/fixtures/       Representative prototype documents from three domains
requirements.txt     Runtime dependencies
requirements-dev.txt Test dependencies, including runtime requirements
requirements-swift.txt Optional Swift client (included in test dependencies)
constraints.txt      Pinned direct and transitive dependency versions
.github/workflows/ci.yml  Tests for master and stacked PRs
```

Both installation paths use `constraints.txt` to keep dependency versions
consistent. When updating dependencies, update the pins together and rerun
`python -m pip check` and `python -m pytest` in a fresh virtual environment.
Virtual environments, Python/test caches and local environment files are
excluded from Git. The `data/` directory remains tracked.

## Basic validation

`POST /api/v1/artifacts/validate` accepts a JSON document and never stores it.
Valid input returns HTTP 200 with `{"valid":true,"errors":[]}`. Malformed JSON
and failed validation return HTTP 422 with the same envelope and errors
containing `path`, `code` and `message`.

From the repository root, with the server running:

```bash
curl -i --user "$API_AUTH_USERNAME" http://localhost:8000/api/v1/artifacts/validate \
  -H 'Content-Type: application/json' \
  --data-binary @tests/fixtures/nga_object_98765.json

curl -i --user "$API_AUTH_USERNAME" http://localhost:8000/api/v1/artifacts/validate \
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
nested entities are not checked against a domain schema. Rate/body-size limits
and production hardening are deferred.

`python -m pytest` exercises all supported types, three representative fixtures,
malformed JSON, invalid fields/contexts and the API response contract. Validation
tests block network connections and run in an empty temporary working directory
to check that no storage/index directories are created.

## Publication, retrieval and search

The data flow is JSON-LD → validation → versioned storage and SQLite index →
retrieval/search API. See [the repository API walkthrough](docs/repository-api.md)
for requests, response semantics, recovery and limitations, and
[storage usage](docs/storage.md) for backend details.

This remains an incremental, single-process implementation, not a production
service. OAuth/OIDC, multi-writer coordination and deployment configuration
are deferred. No demo UI or sample-loading tooling is included.
