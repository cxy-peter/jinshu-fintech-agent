#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v node >/dev/null 2>&1; then
  echo 'Please install Node.js 22 or newer first.' >&2
  exit 1
fi
exec node scripts/manual_deploy.mjs "$@"
