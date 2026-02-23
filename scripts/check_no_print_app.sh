#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT_DIR"

matches=$(grep -R -n --include='*.py' -E '\bprint\(' app || true)
if [[ -n "$matches" ]]; then
  echo "ERROR: print() is not allowed in app/" >&2
  echo "$matches" >&2
  exit 1
fi
