#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
LOG_DIR="${ROOT_DIR}/logs"
PROXY_PORT="${PROXY_PORT:-28880}"

mkdir -p "${LOG_DIR}"

cleanup() {
  if [[ -n "${MITM_PID:-}" ]]; then
    kill "${MITM_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

wait_for_port() {
  local port="$1"
  local name="$2"
  "${VENV_DIR}/bin/python" - "$port" "$name" <<'PY'
import socket
import sys
import time

port = int(sys.argv[1])
name = sys.argv[2]
deadline = time.time() + 20

while time.time() < deadline:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect(("127.0.0.1", port))
        except OSError:
            time.sleep(0.2)
        else:
            print(f"{name} is listening on 127.0.0.1:{port}")
            raise SystemExit(0)

print(f"Timed out waiting for {name} on 127.0.0.1:{port}", file=sys.stderr)
raise SystemExit(1)
PY
}

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip >/dev/null
"${VENV_DIR}/bin/python" -m pip install -r "${ROOT_DIR}/requirements.txt" >/dev/null

"${VENV_DIR}/bin/python" -m unittest tests.test_rewrite_rules tests.test_proxy_components

"${VENV_DIR}/bin/mitmdump" \
  --quiet \
  --listen-host 127.0.0.1 \
  --listen-port "${PROXY_PORT}" \
  --set ssl_insecure=true \
  -s "${ROOT_DIR}/rewrite_addon.py" \
  >"${LOG_DIR}/mitmdump.log" 2>&1 &
MITM_PID="$!"
wait_for_port "${PROXY_PORT}" "mitmproxy"

echo "Positive case: HTTPS request should be rewritten to the real Worker"
POSITIVE_BODY_FILE="/tmp/real-worker-mitm-positive-body.html"
POSITIVE_STATUS="$(curl -skL --proxy "http://127.0.0.1:${PROXY_PORT}" --connect-timeout 10 --max-time 30 -o "${POSITIVE_BODY_FILE}" -w "%{http_code}" "https://huanyuxingqiu.fun/4687.html")"

if [[ "${POSITIVE_STATUS}" != "200" ]]; then
  echo "Expected Worker response status 200, got ${POSITIVE_STATUS}" >&2
  head -n 20 "${POSITIVE_BODY_FILE}" >&2
  exit 1
fi
grep -i "<html" "${POSITIVE_BODY_FILE}" >/dev/null
echo "Worker page returned HTTP ${POSITIVE_STATUS} through mitmproxy."

echo "Negative case: static asset should not be rewritten and should be blocked locally"
STATIC_STATUS="$(curl -sk --proxy "http://127.0.0.1:${PROXY_PORT}" --connect-timeout 5 --max-time 8 -o /tmp/local-mitm-static-body.txt -w "%{http_code}" "https://huanyuxingqiu.fun/app.js" || true)"
if [[ "${STATIC_STATUS}" != "599" ]]; then
  echo "Expected local safety block status 599, got ${STATIC_STATUS}" >&2
  cat /tmp/local-mitm-static-body.txt >&2
  exit 1
fi
grep -F "blocked unrewritten configured test host" /tmp/local-mitm-static-body.txt >/dev/null
echo "Static asset was not rewritten; local safety block returned ${STATIC_STATUS}."

echo "Real Worker MITM rewrite test completed."
