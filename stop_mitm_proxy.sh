#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="${HOME}/Library/Application Support/daoyufan-mitm"
LABEL="com.daoyufan.mitmproxy"
LAUNCH_DOMAIN="gui/$(id -u)"
PLIST_FILE="${SERVICE_DIR}/mitmproxy.plist"

if launchctl bootout "${LAUNCH_DOMAIN}/${LABEL}" >/dev/null 2>&1; then
  echo "Stopped LaunchAgent ${LABEL}."
else
  echo "LaunchAgent ${LABEL} was not running."
fi

rm -f "${PLIST_FILE}" "${ROOT_DIR}/.run/mitmproxy.pid"
