#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -r requirements.txt

if [ ! -d "frontend/node_modules" ]; then
  (cd frontend && npm install)
fi

mkdir -p logs

find_free_port() {
  local port="$1"
  while lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; do
    port=$((port + 1))
  done
  printf '%s\n' "$port"
}

BACKEND_PORT="${BACKEND_PORT:-8765}"
FRONTEND_PORT="${FRONTEND_PORT:-$(find_free_port 5173)}"

cleanup() {
  if [ -n "${BACKEND_PID:-}" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID:-}" ]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Backend port $BACKEND_PORT is already in use." >&2
  exit 1
fi

.venv/bin/python run_backend.py > logs/console-backend.log 2>&1 &
BACKEND_PID=$!

(cd frontend && exec ./node_modules/.bin/vite --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort > ../logs/console-frontend.log 2>&1) &
FRONTEND_PID=$!

cat <<EOF
DaoyuFan console is starting.

Backend:  http://127.0.0.1:$BACKEND_PORT/api/health
Frontend: http://127.0.0.1:$FRONTEND_PORT

Logs:
  logs/console-backend.log
  logs/console-frontend.log

Press Ctrl-C to stop both services.
EOF

wait
