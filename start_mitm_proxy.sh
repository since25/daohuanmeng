#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="${HOME}/Library/Application Support/daoyufan-mitm"
VENV_DIR="${SERVICE_DIR}/.venv"
LOG_DIR="${SERVICE_DIR}/logs"
PROXY_PORT="${PROXY_PORT:-28880}"
LABEL="com.daoyufan.mitmproxy"
LAUNCH_DOMAIN="gui/$(id -u)"
PLIST_FILE="${SERVICE_DIR}/mitmproxy.plist"

mkdir -p "${LOG_DIR}"
cp "${ROOT_DIR}/rewrite_addon.py" "${SERVICE_DIR}/rewrite_addon.py"
cp "${ROOT_DIR}/rewrite_rules.py" "${SERVICE_DIR}/rewrite_rules.py"
cp "${ROOT_DIR}/requirements.txt" "${SERVICE_DIR}/requirements.txt"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Creating mitmproxy virtual environment..."
  python3 -m venv "${VENV_DIR}"
fi

echo "Installing mitmproxy dependencies..."
"${VENV_DIR}/bin/python" -m pip install --no-cache-dir --upgrade pip >/dev/null
"${VENV_DIR}/bin/python" -m pip install --no-cache-dir -r "${SERVICE_DIR}/requirements.txt" >/dev/null

cat >"${PLIST_FILE}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd "${SERVICE_DIR}" &amp;&amp; exec "${VENV_DIR}/bin/mitmdump" --listen-host 127.0.0.1 --listen-port "${PROXY_PORT}" --set ssl_insecure=true --set connection_strategy=lazy -s "${SERVICE_DIR}/rewrite_addon.py"</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>${HOME}</string>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>LOCAL_MITM_BLOCK_UNREWRITTEN</key>
    <string>0</string>
  </dict>
  <key>WorkingDirectory</key>
  <string>${SERVICE_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/mitmdump.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/mitmdump.err.log</string>
</dict>
</plist>
PLIST

if launchctl bootout "${LAUNCH_DOMAIN}/${LABEL}" >/dev/null 2>&1; then
  sleep 1
fi
echo "Registering LaunchAgent ${LABEL}..."
launchctl bootstrap "${LAUNCH_DOMAIN}" "${PLIST_FILE}"
launchctl kickstart -k "${LAUNCH_DOMAIN}/${LABEL}" >/dev/null 2>&1 || true

echo "Waiting for mitmproxy on 127.0.0.1:${PROXY_PORT}..."
"${VENV_DIR}/bin/python" - "${PROXY_PORT}" <<'PY'
import socket
import sys
import time

port = int(sys.argv[1])
deadline = time.time() + 20

while time.time() < deadline:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect(("127.0.0.1", port))
        except OSError:
            time.sleep(0.2)
        else:
            print(f"mitmproxy is listening on 127.0.0.1:{port}")
            raise SystemExit(0)

print(f"Timed out waiting for mitmproxy on 127.0.0.1:{port}", file=sys.stderr)
raise SystemExit(1)
PY

echo "LaunchAgent ${LABEL} started. Log: ${LOG_DIR}/mitmdump.log"
echo "Next: run ./open_chrome_with_mitm.sh or set Chrome proxy to http://127.0.0.1:${PROXY_PORT}"
