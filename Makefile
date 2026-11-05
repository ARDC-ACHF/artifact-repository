.DEFAULT_GOAL := help

PYTHON ?= python3.11
VENV ?= .venv
HOST ?= 127.0.0.1
PORT ?= 8000
VENV_PYTHON := $(VENV)/bin/python
PID_FILE := .uvicorn.pid
COMPOSE ?= docker compose
TEST_IMAGE ?= artifact-repository-test
TEST_ARGS ?=
export HOST PORT

.PHONY: help install install-dev start stop up down stop-local docker-up docker-down docker-logs docker-ps docker-test clean delete-db test

help:
	@printf '%s\n' \
	  'make install      Create a venv and install runtime dependencies' \
	  'make install-dev  Install runtime and development dependencies' \
	  'make start        Run the development server (Ctrl-C to stop)' \
	  'make stop         Stop local and Docker servers; remove the Compose network' \
	  'make up           Alias for make start' \
	  'make down         Alias for make stop' \
	  'make docker-up    Build and start containers in the background' \
	  'make docker-down  Remove Compose containers and networks, preserving data' \
	  'make docker-logs  Follow container logs' \
	  'make docker-ps    Show container status' \
	  'make docker-test  Build and run tests in an isolated disposable container' \
	  'make test         Run the test suite' \
	  'make clean        Remove Python caches, coverage and build output' \
	  'make delete-db    Stop the server and delete the SQLite search index' \
	  'Overrides: PYTHON=python3.11 VENV=.venv HOST=127.0.0.1 PORT=8000'

$(VENV_PYTHON):
	$(PYTHON) -m venv "$(VENV)"

install: $(VENV_PYTHON)
	"$(VENV_PYTHON)" -m pip install -r requirements.txt

install-dev: $(VENV_PYTHON)
	"$(VENV_PYTHON)" -m pip install -r requirements-dev.txt

up: start

down: stop

start:
	@test -x "$(VENV_PYTHON)" || { echo 'Run make install first.'; exit 1; }
	@set -eu; \
	if test -f "$(PID_FILE)" && kill -0 "$$(cat "$(PID_FILE)")" 2>/dev/null; then \
	  echo 'A server PID is already recorded; run make stop first.'; exit 1; \
	fi; \
	echo $$$$ > "$(PID_FILE)"; \
	exec "$(VENV_PYTHON)" -m uvicorn app.main:app --reload --host "$(HOST)" --port "$(PORT)"

stop: stop-local
	@if command -v docker >/dev/null 2>&1; then \
	  $(MAKE) docker-down; \
	else \
	  echo 'Docker is not installed; skipping container shutdown.'; \
	fi

docker-up:
	$(COMPOSE) up --build --detach --wait

docker-down:
	$(COMPOSE) down --remove-orphans

docker-logs:
	$(COMPOSE) logs --follow

docker-ps:
	$(COMPOSE) ps

docker-test:
	docker build --target test --tag "$(TEST_IMAGE)" .
	docker run --rm --network none "$(TEST_IMAGE)" python -m pytest $(TEST_ARGS)

stop-local:
	@set -eu; \
	if ! test -f "$(PID_FILE)"; then echo 'No make-managed server to stop.'; exit 0; fi; \
	pid=$$(cat "$(PID_FILE)"); \
	case "$$pid" in ''|*[!0-9]*|0|1) echo 'Invalid server PID file.'; exit 1;; esac; \
	if kill -0 "$$pid" 2>/dev/null; then \
	  case "$$(ps -p "$$pid" -o command=)" in \
	    *' -m uvicorn app.main:app --reload '*) ;; \
	    *) echo 'Recorded PID is not the development server; refusing to stop it.'; exit 1;; \
	  esac; \
	  kill -TERM "$$pid"; \
	  attempts=0; \
	  while kill -0 "$$pid" 2>/dev/null; do \
	    attempts=$$((attempts + 1)); \
	    if test "$$attempts" -ge 15; then echo 'Server has not stopped; try again later.'; exit 1; fi; \
	    sleep 1; \
	  done; \
	fi; \
	rm -f "$(PID_FILE)"; \
	echo 'Server stopped.'

test:
	"$(VENV_PYTHON)" -m pytest $(TEST_ARGS)

clean:
	find app tests -type d -name __pycache__ -prune -exec rm -rf {} +
	find app tests -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .hypothesis htmlcov
	rm -f .coverage .coverage.* coverage.xml coverage.json

# Keeps artifact snapshots; call RepositoryService.reindex() to restore search.
delete-db: stop
	rm -f data/index.sqlite3 data/index.sqlite3-wal data/index.sqlite3-shm data/index.sqlite3-journal
