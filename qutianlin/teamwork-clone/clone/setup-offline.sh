#!/usr/bin/env bash
set -euo pipefail
clone_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
clone_venv="${1:-$clone_root/../data/runtime-venv}"
python -m venv "$clone_venv"
"$clone_venv/bin/python" -m pip install --no-index --find-links "$clone_root/wheelhouse" -r "$clone_root/requirements.txt"
printf 'Offline environment ready: %s\n' "$clone_venv"
