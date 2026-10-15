#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
cd "$(dirname "$0")"
export WEBSITEBENCH_SMTP_HOST="${WEBSITEBENCH_SMTP_HOST:-127.0.0.1}"
export WEBSITEBENCH_SMTP_PORT="${WEBSITEBENCH_SMTP_PORT:-1025}"
export WEBSITEBENCH_SMTP_FROM="${WEBSITEBENCH_SMTP_FROM:-no-reply@linear.clone.test}"
export LINEAR_DATA_DIR="${LINEAR_DATA_DIR:-$PWD/../data}"
exec python -m uvicorn server:app --host 127.0.0.1 --port "${PORT:-18140}"
