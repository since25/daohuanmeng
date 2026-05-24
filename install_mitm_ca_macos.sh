#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
CERT_PATH="${HOME}/.mitmproxy/mitmproxy-ca-cert.cer"
KEYCHAIN_PATH="${HOME}/Library/Keychains/login.keychain-db"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip >/dev/null
"${VENV_DIR}/bin/python" -m pip install -r "${ROOT_DIR}/requirements.txt" >/dev/null

if [[ ! -f "${CERT_PATH}" ]]; then
  echo "Generating mitmproxy CA certificate..."
  "${VENV_DIR}/bin/mitmdump" --quiet --listen-host 127.0.0.1 --listen-port 18080 >/tmp/daoyufan-mitm-ca.log 2>&1 &
  MITM_CERT_PID="$!"
  sleep 2
  kill "${MITM_CERT_PID}" >/dev/null 2>&1 || true
  wait "${MITM_CERT_PID}" >/dev/null 2>&1 || true
fi

if [[ ! -f "${CERT_PATH}" ]]; then
  echo "Could not find generated certificate at ${CERT_PATH}" >&2
  exit 1
fi

echo "Installing mitmproxy CA certificate into login keychain:"
echo "${CERT_PATH}"
security add-trusted-cert -d -r trustRoot -k "${KEYCHAIN_PATH}" "${CERT_PATH}"
echo "Certificate installed. Restart Chrome after installation."
