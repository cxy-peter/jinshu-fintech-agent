#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
repo="cxy-peter/jinshu-fintech-agent"
gh auth status
python -m pytest -q
python scripts/verify_source.py
if gh repo view "$repo" --json name >/dev/null 2>&1; then echo "Repository exists; refusing to overwrite"; exit 1; fi
if [ -d .git ]; then echo "Existing .git: review manually"; exit 1; fi
read -r -p 'Confirm reviewed private publication (type PRIVATE): ' reply
[ "$reply" = PRIVATE ] || exit 1
git init -b main
git add .
git commit -m 'Add Jinshu fintech workflows and verified bounded evolution loop'
gh repo create "$repo" --private --source . --remote origin --push
gh repo view "$repo" --web
