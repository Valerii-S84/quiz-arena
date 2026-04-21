#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT_DIR"

DOCKERIGNORE_FILE=".dockerignore"

if [[ ! -f "$DOCKERIGNORE_FILE" ]]; then
  echo "ERROR: ${DOCKERIGNORE_FILE} not found" >&2
  exit 1
fi

required_patterns=(
  ".env"
  ".env.*"
  ".env.backup_*"
  "**/.env"
  "**/.env.*"
  "**/.env.backup_*"
)

missing_patterns=()
for pattern in "${required_patterns[@]}"; do
  if ! grep -Fxq "$pattern" "$DOCKERIGNORE_FILE"; then
    missing_patterns+=("$pattern")
  fi
done

if [[ ${#missing_patterns[@]} -gt 0 ]]; then
  echo "ERROR: ${DOCKERIGNORE_FILE} is missing required secret-exclusion patterns:" >&2
  printf '  - %s\n' "${missing_patterns[@]}" >&2
  exit 1
fi
