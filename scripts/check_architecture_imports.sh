#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT_DIR"

domain_dirs=(
  app/core
  app/db
  app/economy
  app/game
  app/services
)

matches=""
for dir in "${domain_dirs[@]}"; do
  if [[ -d "$dir" ]]; then
    found=$(grep -R -n --include='*.py' -E '^\s*(from|import)\s+app\.bot' "$dir" || true)
    if [[ -n "$found" ]]; then
      matches+="$found"$'\n'
    fi
  fi

done

if [[ -n "$matches" ]]; then
  echo "ERROR: domain modules must not import app.bot" >&2
  echo "$matches" >&2
  exit 1
fi
