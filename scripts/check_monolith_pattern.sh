#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT_DIR"

warn=0

if [[ -d app ]]; then
  while IFS= read -r -d '' file; do
    lines=$(wc -l < "$file" | tr -d ' ')
    if (( lines < 180 )); then
      continue
    fi
    def_count=$(grep -c '^def ' "$file" || true)
    if_count=$(grep -c '^if ' "$file" || true)
    if (( def_count > 5 && if_count > 5 )); then
      echo "WARNING: Potential God File detected (${lines} lines, def=${def_count}, if=${if_count}): ${file}" >&2
      warn=1
    fi
  done < <(find app -type f -name '*.py' -print0)
fi

exit 0
