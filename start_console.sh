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

cleanup() {
  if [ -n "${BACKEND_PID:-}" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID:-}" ]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

.venv/bin/python run_backend.py > logs/console-backend.log 2>&1 &
BACKEND_PID=$!

(cd frontend && npm run dev > ../logs/console-frontend.log 2>&1) &
FRONTEND_PID=$!

cat <<EOF
DaoyuFan console is starting.

Backend:  http://127.0.0.1:8765/api/health
Frontend: http://127.0.0.1:5173

Logs:
  logs/console-backend.log
  logs/console-frontend.log

Press Ctrl-C to stop both services.
EOF

wait
