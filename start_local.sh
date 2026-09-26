#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  if command -v python3.12 >/dev/null 2>&1; then python3.12 -m venv .venv
  else python3 -m venv .venv
  fi
fi
.venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else "Python 3.12 is required. Create a Python 3.12 .venv before starting.")'
.venv/bin/python -m pip install -r requirements.txt
env_args=()
if [[ -f .env ]]; then env_args=(--env-file .env); fi
printf '%s\n' 'Jinshu V8.1: complete shared backend at http://127.0.0.1:8766' 'Missing service/model settings are shown on the setup page; no offline fallback.'
exec .venv/bin/python -m uvicorn index:app --host 127.0.0.1 --port 8766 "${env_args[@]}"
