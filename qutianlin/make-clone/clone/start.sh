#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export WEBSITEBENCH_SITE_BACKEND_RUNTIME="${WEBSITEBENCH_SITE_BACKEND_RUNTIME:-$(pwd)/backend/runtime.json}"
export WEBSITEBENCH_SITE_BACKEND_DATABASE="${WEBSITEBENCH_SITE_BACKEND_DATABASE:-$(pwd)/../data/make.sqlite3}"
export WEBSITEBENCH_SMTP_HOST="${WEBSITEBENCH_SMTP_HOST:-127.0.0.1}"
export WEBSITEBENCH_SMTP_PORT="${WEBSITEBENCH_SMTP_PORT:-1025}"
export WEBSITEBENCH_SMTP_FROM="${WEBSITEBENCH_SMTP_FROM:-no-reply@make.clone.test}"
exec python -m uvicorn app:app --host "${HOST:-127.0.0.1}" --port "${PORT:-18170}"
