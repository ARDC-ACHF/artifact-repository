#!/usr/bin/env bash
# One-command stakeholder demo: set up Python + frontend, seed demo data, start the server.
#
#   ./run_demo.sh                 # set up what is missing/stale, re-seed, serve on http://localhost:8000
#   ./run_demo.sh --setup-only    # do everything except starting the server
#
# Every run re-seeds demo_data/ from scratch (seed_demo.py --reset), so the demo
# edit history (backdated v1 -> v2 -> v3) is always intact. Records published
# through the API in an earlier run are discarded.
#
# Options:  --port N  --rebuild  --recreate-venv  --setup-only  -h|--help
#           (--reset is accepted for compatibility; resetting is now the default)
# Env:      PYTHON=/path/to/python3.11   VENV_DIR=.venv   PORT=8000
#           API_AUTH_USERNAME / API_AUTH_PASSWORD (otherwise generated per run)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
HOST="127.0.0.1"
VENV_DIR="${VENV_DIR:-$ROOT/.venv}"
DATA_DIR="$ROOT/demo_data"
FRONTEND_DIR="$ROOT/frontend"
CREDENTIALS_FILE="$DATA_DIR/credentials.env"
NODE_MIN="20.19.0"
REBUILD=0 RECREATE_VENV=0 SETUP_ONLY=0

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) [[ $# -ge 2 ]] || die "--port needs a value"; PORT="$2"; shift 2 ;;
    --port=*) PORT="${1#*=}"; shift ;;
    --reset) shift ;;  # always on; kept so older instructions still work
    --rebuild) REBUILD=1; shift ;;
    --recreate-venv) RECREATE_VENV=1; shift ;;
    --setup-only) SETUP_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
done
[[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT > 0 && PORT < 65536 )) || die "invalid port: $PORT"

check_port() {
  if (exec 3<>"/dev/tcp/$HOST/$PORT") 2>/dev/null; then
    die "port $PORT on $HOST is already in use (stop the other server or use --port N)"
  fi
}
[[ $SETUP_ONLY -eq 1 ]] || check_port

# version_ge A B  -> true when dotted version A >= B
version_ge() {
  local IFS=.
  local -a a=($1) b=($2)
  local i
  for i in 0 1 2; do
    local x="${a[i]:-0}" y="${b[i]:-0}"
    (( 10#$x > 10#$y )) && return 0
    (( 10#$x < 10#$y )) && return 1
  done
  return 0
}

py_version() { "$1" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null; }

# --- Python ------------------------------------------------------------------
find_python() {
  local candidate
  for candidate in ${PYTHON:-} python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      local v; v="$(py_version "$candidate")" || continue
      if version_ge "$v" "3.11.0"; then command -v "$candidate"; return 0; fi
    fi
  done
  return 1
}

venv_python="$VENV_DIR/bin/python"
venv_ok() {
  [[ -x "$venv_python" ]] || return 1
  local v; v="$(py_version "$venv_python")" || return 1
  version_ge "$v" "3.11.0"
}

if [[ $RECREATE_VENV -eq 1 ]] || ! venv_ok; then
  BASE_PYTHON="$(find_python)" || die "Python 3.11+ is required (3.11 is the tested version).
  Install it with:  brew install python@3.11
  or point the script at an interpreter:  PYTHON=/path/to/python3.11 ./run_demo.sh"
  if [[ -e "$VENV_DIR" ]]; then
    say "Recreating $VENV_DIR (missing, broken, older than 3.11 or --recreate-venv)"
    rm -rf "$VENV_DIR"
  fi
  say "Creating virtual environment with $BASE_PYTHON ($(py_version "$BASE_PYTHON"))"
  "$BASE_PYTHON" -m venv "$VENV_DIR"
fi
VENV_PY_VERSION="$(py_version "$venv_python")"
if [[ "$VENV_PY_VERSION" != 3.11.* ]]; then
  warn "$VENV_DIR uses Python $VENV_PY_VERSION; 3.11 is the tested version (use --recreate-venv to rebuild it with python3.11)."
fi

# Reinstall whenever the requirements, constraints or interpreter change.
REQ_STAMP="$VENV_DIR/.demo-requirements.sha256"
req_hash="$( { cat requirements.txt constraints.txt; echo "$VENV_PY_VERSION"; } | shasum -a 256 | cut -d' ' -f1)"
if [[ ! -f "$REQ_STAMP" || "$(cat "$REQ_STAMP")" != "$req_hash" ]]; then
  say "Installing Python requirements into $VENV_DIR"
  "$venv_python" -m pip install --quiet --disable-pip-version-check -r requirements.txt
  echo "$req_hash" > "$REQ_STAMP"
else
  say "Python requirements up to date ($VENV_DIR, Python $VENV_PY_VERSION)"
fi

# --- Node --------------------------------------------------------------------
node_ok() { command -v node >/dev/null 2>&1 && version_ge "$(node -v | sed 's/^v//')" "$NODE_MIN"; }

if ! node_ok; then
  # Non-interactive shells often lack nvm's PATH; pick the newest suitable nvm-installed Node.
  nvm_root="${NVM_DIR:-$HOME/.nvm}/versions/node"
  if [[ -d "$nvm_root" ]]; then
    best=""
    for dir in "$nvm_root"/v*/; do
      v="$(basename "$dir")"; v="${v#v}"
      [[ -x "$dir/bin/node" ]] && version_ge "$v" "$NODE_MIN" || continue
      if [[ -z "$best" ]] || version_ge "$v" "$best"; then best="$v"; fi
    done
    [[ -n "$best" ]] && export PATH="$nvm_root/v$best/bin:$PATH"
  fi
fi
node_ok || die "Node.js $NODE_MIN+ is required to build the frontend (found: $(node -v 2>/dev/null || echo none)).
  Install it with:  brew install node
  or with nvm:      nvm install 22 && nvm use 22"
say "Using Node $(node -v) ($(command -v node))"

# --- Frontend ----------------------------------------------------------------
cd "$FRONTEND_DIR"
if [[ ! -f node_modules/.package-lock.json || package-lock.json -nt node_modules/.package-lock.json ]]; then
  say "Installing frontend dependencies (npm ci)"
  npm ci --no-audit --no-fund --loglevel=error
fi
needs_build=$REBUILD
if [[ ! -f dist/index.html ]]; then
  needs_build=1
elif [[ -n "$(find src index.html vite.config.js package.json package-lock.json -newer dist/index.html -print -quit)" ]]; then
  needs_build=1
fi
if [[ $needs_build -eq 1 ]]; then
  say "Building frontend (npm run build)"
  npm run build --silent
else
  say "Frontend build up to date (frontend/dist)"
fi
cd "$ROOT"

# --- Data --------------------------------------------------------------------
# --reset clears only demo_data/artifacts and the search index (credentials.env
# is kept), then publishes the base records and backdated revisions in order.
say "Re-seeding demo records into demo_data/ (with demo edit history)"
"$venv_python" scripts/seed_demo.py --data-dir "$DATA_DIR" --reset

if [[ $SETUP_ONLY -eq 1 ]]; then
  say "Setup complete (--setup-only); start later with ./run_demo.sh"
  exit 0
fi

check_port

# --- Credentials for writes (never printed) -------------------------------------
if [[ -n "${API_AUTH_USERNAME:-}" && -n "${API_AUTH_PASSWORD:-}" ]]; then
  say "Using API_AUTH_USERNAME / API_AUTH_PASSWORD from the environment for writes"
  rm -f "$CREDENTIALS_FILE"
  CREDENTIALS_HINT="use the API_AUTH_USERNAME / API_AUTH_PASSWORD you exported"
else
  API_AUTH_USERNAME="demo"
  API_AUTH_PASSWORD="$("$venv_python" -c 'import secrets; print(secrets.token_urlsafe(24))')"
  rm -f "$CREDENTIALS_FILE"
  (umask 077; printf 'API_AUTH_USERNAME=%s\nAPI_AUTH_PASSWORD=%s\n' \
    "$API_AUTH_USERNAME" "$API_AUTH_PASSWORD" > "$CREDENTIALS_FILE")
  CREDENTIALS_HINT="generated for this run in demo_data/credentials.env (mode 600):
      set -a; . demo_data/credentials.env; set +a"
fi

cat <<EOF

  ACHF Explorer demo  ->  http://localhost:$PORT
    API docs:      http://localhost:$PORT/docs
    Try searching: Godot, Namatjira, Belvoir, Streeton, Doll
    Version history: Albert Namatjira (2 versions), Waiting for Godot 2013 (2),
                     Shearing the Rams (3)
    Reads are public (DEMO_PUBLIC_READ=1); writes need Basic auth, $CREDENTIALS_HINT
      curl -u "\$API_AUTH_USERNAME:\$API_AUTH_PASSWORD" -H 'Content-Type: application/json' \\
        --data-binary @sample_data/demo/<record>.json http://localhost:$PORT/api/v1/artifacts
    Listening on $HOST only. Press Ctrl-C to stop.

EOF

export API_AUTH_USERNAME API_AUTH_PASSWORD
export DEMO_PUBLIC_READ=1 REPOSITORY_DATA_DIR="$DATA_DIR"
exec "$venv_python" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
