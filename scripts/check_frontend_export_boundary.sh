#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR=${1:-frontend}

usage() {
  cat <<'USAGE'
Usage: scripts/check_frontend_export_boundary.sh [target-dir]

Verifies that a frontend directory is self-contained as a future standalone
repo root and that exported docs do not accidentally depend on monorepo-only
automation without saying so explicitly.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "ERROR: target directory does not exist: $TARGET_DIR" >&2
  exit 1
fi

required_entries=(
  ".dockerignore"
  ".env.example"
  ".gitignore"
  "Dockerfile"
  "README.md"
  "app"
  "lib"
  "next.config.mjs"
  "package-lock.json"
  "package.json"
  "SPLIT_RUNBOOK.md"
  "tsconfig.json"
)

missing_entries=()
for entry in "${required_entries[@]}"; do
  if [[ ! -e "$TARGET_DIR/$entry" ]]; then
    missing_entries+=("$entry")
  fi
done

if [[ ${#missing_entries[@]} -gt 0 ]]; then
  echo "ERROR: frontend export boundary is missing required entries:" >&2
  printf '  - %s\n' "${missing_entries[@]}" >&2
  exit 1
fi

forbidden_top_level_entries=(
  ".agent"
  "QuizBank"
  "alembic"
  "app/main.py"
  "deploy"
  "docker-compose.prod.yml"
  "frontend"
)

present_forbidden_entries=()
for entry in "${forbidden_top_level_entries[@]}"; do
  if [[ -e "$TARGET_DIR/$entry" ]]; then
    present_forbidden_entries+=("$entry")
  fi
done

if [[ ${#present_forbidden_entries[@]} -gt 0 ]]; then
  echo "ERROR: frontend export boundary still contains monorepo-only entries:" >&2
  printf '  - %s\n' "${present_forbidden_entries[@]}" >&2
  exit 1
fi

runbook_file="$TARGET_DIR/SPLIT_RUNBOOK.md"
monorepo_disclaimer="These scripts exist only in the source monorepo before extraction; they are not part of the exported frontend repo."

if rg -n "scripts/" "$runbook_file" >/dev/null 2>&1; then
  if ! grep -Fq "$monorepo_disclaimer" "$runbook_file"; then
    echo "ERROR: SPLIT_RUNBOOK.md references monorepo scripts without the required disclaimer." >&2
    exit 1
  fi
fi

if rg -n "scripts/(split_frontend_dry_run|export_frontend_repo)\\.sh" \
  "$TARGET_DIR" --glob '!SPLIT_RUNBOOK.md' >/dev/null 2>&1; then
  echo "ERROR: monorepo-only split scripts are referenced outside SPLIT_RUNBOOK.md." >&2
  exit 1
fi

echo "OK: frontend export boundary is self-contained."
echo "target: $TARGET_DIR"
