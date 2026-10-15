#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export WEBSITEBENCH_SMTP_HOST="${WEBSITEBENCH_SMTP_HOST:-127.0.0.1}"
export WEBSITEBENCH_SMTP_PORT="${WEBSITEBENCH_SMTP_PORT:-1025}"
export WEBSITEBENCH_SMTP_FROM="${WEBSITEBENCH_SMTP_FROM:-no-reply@cal.clone.test}"
export WEBSITEBENCH_SITE_BACKEND_RUNTIME="$PWD/backend/runtime.json"
export WEBSITEBENCH_SITE_BACKEND_DATABASE="${CAL_DATA_DIR:-$PWD/data}/cal.sqlite3"
exec .venv/bin/python -m uvicorn app:app --host "${HOST:-127.0.0.1}" --port "${PORT:-18210}" --no-access-log
