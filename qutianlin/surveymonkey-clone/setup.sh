#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
"${PYTHON:-python3.12}" -m venv .venv
export PYTHONPATH="$PWD/clone/vendor${PYTHONPATH:+:$PYTHONPATH}"
if [[ "$(basename "$PWD")" == "ifttt-clone" ]]; then
  echo 'Ready: bash start.sh'; exit 0
fi
if .venv/bin/python -c 'import fastapi, uvicorn' 2>/dev/null; then
  echo 'Ready: bash start.sh'; exit 0
fi
req=clone/requirements.txt
[[ -f "$req" ]] || req=requirements.txt
if [[ -d clone/wheelhouse ]]; then
  .venv/bin/python -m pip install --no-index --find-links clone/wheelhouse -r "$req"
elif [[ -d clone/wheels ]]; then
  .venv/bin/python -m pip install --no-index --find-links clone/wheels -r "$req"
else
  .venv/bin/python -m pip install -r "$req"
fi
echo 'Ready: bash start.sh'
