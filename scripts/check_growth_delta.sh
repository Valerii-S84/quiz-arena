#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CI:-}" ]] && [[ -z "${GITHUB_ACTIONS:-}" ]] && [[ -z "${FORCE_GROWTH_CHECK:-}" ]]; then
  echo "Skipping growth delta guard (non-CI)." >&2
  exit 0
fi

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

if ! ensure_base_ref; then
  if [[ -n "${CI:-}" || -n "${GITHUB_ACTIONS:-}" ]]; then
    echo "ERROR: Growth delta guard requires ${BASE_REF} in CI." >&2
    exit 1
  fi
  echo "Skipping growth delta guard (base ref not available)." >&2
  exit 0
fi

fail=0

while IFS=$'\t' read -r added deleted file; do
  [[ -z "$file" ]] && continue
  if [[ "$added" == "-" ]]; then
    continue
  fi
  case "$file" in
    app/*.py|app/**/*.py)
      if (( added > 50 )); then
        if [[ -f "$file" ]]; then
          lines=$(wc -l < "$file" | tr -d ' ')
          if (( lines > 180 )); then
            echo "ERROR: File growing too fast. Split before expanding. (${file}: +${added}, ${lines} lines)" >&2
            fail=1
          fi
        fi
      fi
      ;;
  esac

done < <(git diff --numstat "$BASE_REF"...HEAD)

exit $fail
