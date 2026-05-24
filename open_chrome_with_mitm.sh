#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROXY_PORT="${PROXY_PORT:-8080}"
PROFILE_DIR="${ROOT_DIR}/.chrome-mitm-profile"
TARGET_URL="${1:-https://daoyu.fan/4687.html}"

mkdir -p "${PROFILE_DIR}"

if ! nc -z 127.0.0.1 "${PROXY_PORT}" >/dev/null 2>&1; then
  echo "Proxy is not listening on 127.0.0.1:${PROXY_PORT}; starting it first..."
  PROXY_PORT="${PROXY_PORT}" "${ROOT_DIR}/start_mitm_proxy.sh"
fi

open -na "Google Chrome" --args \
  "--user-data-dir=${PROFILE_DIR}" \
  "--proxy-server=http://127.0.0.1:${PROXY_PORT}" \
  "${TARGET_URL}"
