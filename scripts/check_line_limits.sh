#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT_DIR"

BASE_REF=${BASE_REF:-origin/main}

ensure_base_ref() {
  if git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    return 0
  fi
  if [[ "$BASE_REF" == "origin/main" ]] && git remote get-url origin >/dev/null 2>&1; then
    git fetch origin main --depth=1 >/dev/null 2>&1 || true
  fi
  git rev-parse --verify "$BASE_REF" >/dev/null 2>&1
}

list_changed_files() {
  if ensure_base_ref; then
    git diff --name-only "$BASE_REF"...HEAD
    return 0
  fi
  git diff --name-only --cached
  git status --porcelain | awk '{print $2}'
}

list_added_files() {
  if ensure_base_ref; then
    git diff --name-status --diff-filter=A "$BASE_REF"...HEAD | awk '{print $2}'
    return 0
  fi
  git diff --name-status --diff-filter=A --cached | awk '{print $2}'
  git status --porcelain | awk '$1 ~ /^\?\?$/ {print $2}'
}

has_size_exception_marker() {
  local marker="[APPROVED_SIZE_EXCEPTION]"
  if [[ -n "${PR_DESCRIPTION:-}" ]] && [[ "${PR_DESCRIPTION}" == *"${marker}"* ]]; then
    return 0
  fi
  if [[ -z "${GITHUB_EVENT_PATH:-}" ]]; then
    return 1
  fi
  if [[ ! -f "${GITHUB_EVENT_PATH}" ]]; then
    return 1
  fi
  python3 - <<'PY'
import json
import os
import sys

marker = "[APPROVED_SIZE_EXCEPTION]"
path = os.environ.get("GITHUB_EVENT_PATH")
if not path:
    sys.exit(1)
try:
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
except Exception:
    sys.exit(1)
body = (payload.get("pull_request") or {}).get("body") or ""
if marker in body:
    sys.exit(0)
sys.exit(1)
PY
}

is_ci_pr() {
  if [[ -z "${CI:-}" ]] && [[ -z "${GITHUB_ACTIONS:-}" ]]; then
    return 1
  fi
  if [[ "${GITHUB_EVENT_NAME:-}" == pull_request* ]]; then
    return 0
  fi
  return 1
}

line_count() {
  wc -l < "$1" | tr -d ' '
}

warn_soft_limit() {
  local file=$1
  local lines=$2
  if (( lines > 200 )); then
    echo "WARNING: app file over 200 lines (${lines}): ${file}" >&2
  fi
}

fail=0

# Soft warnings for all app files
if [[ -d app ]]; then
  while IFS= read -r -d '' file; do
    lines=$(line_count "$file")
    warn_soft_limit "$file" "$lines"
  done < <(find app -type f -name '*.py' -print0)
fi

# Hard limits for changed files
changed_files=()
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  changed_files+=("$file")
done < <(list_changed_files | sort -u)

size_exception_allowed=0
if is_ci_pr && has_size_exception_marker; then
  size_exception_allowed=1
fi

for file in "${changed_files[@]}"; do
  [[ -f "$file" ]] || continue

  case "$file" in
    app/*.py|app/**/*.py)
      lines=$(line_count "$file")
      if (( lines > 250 )); then
        echo "ERROR: app file exceeds 250 lines (${lines}): ${file}" >&2
        fail=1
      fi
      if (( lines > 220 )); then
        if (( size_exception_allowed == 0 )); then
          echo "ERROR: app file exceeds 220 lines without [APPROVED_SIZE_EXCEPTION] (${lines}): ${file}" >&2
          fail=1
        fi
      fi
      ;;
    tests/*.py|tests/**/*.py)
      lines=$(line_count "$file")
      if (( lines > 400 )); then
        echo "ERROR: tests file exceeds 400 lines (${lines}): ${file}" >&2
        fail=1
      fi
      ;;
    tools/*.py|tools/**/*.py)
      lines=$(line_count "$file")
      if (( lines > 300 )); then
        echo "ERROR: tools file exceeds 300 lines (${lines}): ${file}" >&2
        fail=1
      fi
      ;;
  esac

done

# Bot handler immunity for newly added files
added_files=()
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  added_files+=("$file")


done < <(list_added_files | sort -u)

for file in "${added_files[@]}"; do
  [[ -f "$file" ]] || continue
  case "$file" in
    app/bot/handlers/*.py|app/bot/handlers/**/*.py)
      lines=$(line_count "$file")
      if (( lines > 180 )); then
        echo "ERROR: new bot handler exceeds 180 lines (${lines}): ${file}" >&2
        fail=1
      fi
      ;;
  esac

done

exit $fail
