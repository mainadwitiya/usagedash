#!/usr/bin/env bash
set -euo pipefail

REPO="${USAGEDASH_REPO:-adwitiya24/usagedash}"
VERSION="${USAGEDASH_VERSION:-latest}"
WITH_TRAY="${USAGEDASH_WITH_TRAY:-0}"
BIN_DIR="${HOME}/.local/bin"
STATE_DIR="${HOME}/.local/state/usagedash"
CONFIG_DIR="${HOME}/.config/usagedash"

mkdir -p "${BIN_DIR}" "${STATE_DIR}" "${CONFIG_DIR}"

if [[ "${VERSION}" == "latest" ]]; then
  BASE_URL="https://github.com/${REPO}/releases/latest/download"
else
  BASE_URL="https://github.com/${REPO}/releases/download/${VERSION}"
fi

curl -fsSL "${BASE_URL}/usagedash-linux-x86_64" -o "${BIN_DIR}/usagedash"
chmod +x "${BIN_DIR}/usagedash"

if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
  "${BIN_DIR}/usagedash" doctor >/dev/null 2>&1 || true
fi

echo "Installed usagedash to ${BIN_DIR}/usagedash"
echo "Add ${BIN_DIR} to PATH if needed."

if [[ "${WITH_TRAY}" == "1" ]]; then
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \
      "iwr -useb https://raw.githubusercontent.com/${REPO}/main/scripts/install-tray.ps1 | iex"
    echo "Triggered Windows tray installer."
  else
    echo "powershell.exe is unavailable from this WSL instance."
    echo "Run this in Windows PowerShell:"
    echo "  iwr -useb https://raw.githubusercontent.com/${REPO}/main/scripts/install-tray.ps1 | iex"
  fi
fi
