#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  echo "Creating backend virtual environment..."
  python3 -m venv .venv
fi

echo "Installing backend dependencies..."
.venv/bin/python -m pip install --no-cache-dir -r requirements.txt

if [ ! -d "frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
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
PROXY_PORT="${PROXY_PORT:-28880}"
START_PROXY="${START_PROXY:-1}"
MITM_LOG_DIR="${HOME}/Library/Application Support/daoyufan-mitm/logs"
PROXY_STARTED=0

cleanup() {
  if [ -n "${LOG_TAIL_PID:-}" ]; then
    kill "$LOG_TAIL_PID" 2>/dev/null || true
  fi
  if [ -n "${BACKEND_PID:-}" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID:-}" ]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [ "$PROXY_STARTED" = "1" ]; then
    "${ROOT_DIR}/stop_mitm_proxy.sh" || true
  fi
}
trap cleanup EXIT INT TERM

if lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Backend port $BACKEND_PORT is already in use." >&2
  exit 1
fi

if [ "$START_PROXY" = "1" ]; then
  echo "Starting MITM proxy on 127.0.0.1:${PROXY_PORT}..."
  PROXY_STARTED=1
  PROXY_PORT="$PROXY_PORT" "${ROOT_DIR}/start_mitm_proxy.sh"
  PROXY_STATUS="http://127.0.0.1:$PROXY_PORT"
else
  echo "Skipping MITM proxy startup because START_PROXY=0."
  PROXY_STATUS="not started (START_PROXY=0)"
fi

PYTHONUNBUFFERED=1 .venv/bin/python run_backend.py > logs/console-backend.log 2>&1 &
BACKEND_PID=$!

(cd frontend && exec ./node_modules/.bin/vite --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort > ../logs/console-frontend.log 2>&1) &
FRONTEND_PID=$!

TAIL_LOGS=(
  "logs/console-backend.log"
  "logs/console-frontend.log"
)
if [ "$START_PROXY" = "1" ]; then
  TAIL_LOGS+=(
    "${MITM_LOG_DIR}/mitmdump.log"
    "${MITM_LOG_DIR}/mitmdump.err.log"
  )
fi
tail -n 0 -F "${TAIL_LOGS[@]}" &
LOG_TAIL_PID=$!

cat <<EOF
DaoyuFan console is starting.

Backend:  http://127.0.0.1:$BACKEND_PORT/api/health
Frontend: http://127.0.0.1:$FRONTEND_PORT
Proxy:    $PROXY_STATUS

Logs:
  logs/console-backend.log
  logs/console-frontend.log
  $MITM_LOG_DIR/mitmdump.log (when START_PROXY=1)
  $MITM_LOG_DIR/mitmdump.err.log (when START_PROXY=1)

Press Ctrl-C to stop all services.
Use START_PROXY=0 ./start_console.sh to run only the console.
EOF

wait
