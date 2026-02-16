#!/usr/bin/env bash
set -euo pipefail

REPO="${USAGEDASH_REPO:-mainadwitiya/usagedash}"
WITH_TRAY="${USAGEDASH_WITH_TRAY:-0}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install from https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

uv tool install --upgrade "git+https://github.com/${REPO}.git"

echo "Installed usagedash. Run: usagedash dashboard"

if [[ "${WITH_TRAY}" == "1" ]]; then
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \
      "iwr -useb https://raw.githubusercontent.com/${REPO}/main/scripts/install-tray.ps1 | iex"
  else
    echo "Run this in Windows PowerShell to install tray:"
    echo "iwr -useb https://raw.githubusercontent.com/${REPO}/main/scripts/install-tray.ps1 | iex"
  fi
fi
