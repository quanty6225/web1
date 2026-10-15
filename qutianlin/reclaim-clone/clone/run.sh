#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/vendor:$PWD${PYTHONPATH:+:$PYTHONPATH}"
exec python -m uvicorn server:app --host 127.0.0.1 --port "${PORT:-18200}"
