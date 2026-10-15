#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/vendor${PYTHONPATH:+:$PYTHONPATH}"
export WEBSITEBENCH_SMTP_HOST="${WEBSITEBENCH_SMTP_HOST:-127.0.0.1}"
export WEBSITEBENCH_SMTP_PORT="${WEBSITEBENCH_SMTP_PORT:-1025}"
export WEBSITEBENCH_SMTP_FROM="${WEBSITEBENCH_SMTP_FROM:-no-reply@ticktick.clone.test}"
export TICKTICK_DATA_DIR="${TICKTICK_DATA_DIR:-$PWD/data}"
exec python -m uvicorn app:app --host "${HOST:-127.0.0.1}" --port "${PORT:-18120}"
