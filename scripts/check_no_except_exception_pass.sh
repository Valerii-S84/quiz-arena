#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT_DIR"

matches=$(grep -R -n --include='*.py' -E 'except Exception:\s*pass' \
  --exclude-dir=.git \
  --exclude-dir=.venv \
  --exclude-dir=__pycache__ \
  --exclude-dir=.mypy_cache \
  --exclude-dir=.pytest_cache \
  --exclude-dir=.ruff_cache \
  --exclude-dir=.tmp \
  . || true)

if [[ -n "$matches" ]]; then
  echo "ERROR: 'except Exception: pass' is not allowed" >&2
  echo "$matches" >&2
  exit 1
fi
