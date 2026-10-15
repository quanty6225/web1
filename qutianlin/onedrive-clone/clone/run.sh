#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export ONEDRIVE_DATA_DIR="${ONEDRIVE_DATA_DIR:-$PWD/data}"
export WEBSITEBENCH_SMTP_HOST="${WEBSITEBENCH_SMTP_HOST:-127.0.0.1}"
export WEBSITEBENCH_SMTP_PORT="${WEBSITEBENCH_SMTP_PORT:-1025}"
export WEBSITEBENCH_SMTP_FROM="${WEBSITEBENCH_SMTP_FROM:-no-reply@onedrive.clone.test}"
exec python -S server.py
