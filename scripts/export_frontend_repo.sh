#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT_DIR"

REF=${REF:-main}
STRATEGY=${STRATEGY:-filter-repo}
OUTPUT_DIR=${OUTPUT_DIR:-"$ROOT_DIR/.tmp/frontend-repo-export"}
REMOTE_URL=${REMOTE_URL:-}
RUN_INSTALL=1
RUN_CI=1
INCLUDE_WORKING_TREE=0
CLEANUP=0

usage() {
  cat <<'USAGE'
Usage: scripts/export_frontend_repo.sh [options]

Creates a local standalone frontend repository from the current monorepo
history without pushing anywhere. By default it uses the recommended
`filter-repo` strategy and runs frontend validation inside the exported repo.

Options:
  --ref <git-ref>          Source ref for the split history (default: main)
  --strategy <name>        Extraction strategy: filter-repo | subtree
                           (default: filter-repo)
  --output-dir <path>      Output directory for the standalone repo
                           (default: .tmp/frontend-repo-export)
  --remote-url <url>       Configure `origin` in the exported repo without push
  --include-working-tree   Overlay the current frontend/ working tree onto the
                           exported repo after history extraction
  --skip-install           Skip `npm ci`
  --skip-ci                Skip `npm run ci`
  --cleanup                Remove the exported repo after a successful run
  -h, --help               Show this help
USAGE
}

cleanup_path() {
  local path=$1
  local absolute_path

  if [[ -z "$path" || ! -e "$path" ]]; then
    return 0
  fi

  absolute_path="$path"
  if [[ "$absolute_path" != /* ]]; then
    absolute_path="$(cd "$(dirname "$absolute_path")" && pwd)/$(basename "$absolute_path")"
  fi

  if command -v wslpath >/dev/null 2>&1 && command -v cmd.exe >/dev/null 2>&1; then
    if [[ "$absolute_path" == /mnt/* ]]; then
      local windows_output_dir
      windows_output_dir=$(wslpath -w "$absolute_path")
      cmd.exe /c rmdir /s /q "$windows_output_dir" >/dev/null 2>&1 || true
    fi
  fi

  if [[ -e "$absolute_path" ]]; then
    rm -rf "$absolute_path"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --ref requires a value" >&2
        exit 2
      fi
      REF="$2"
      shift 2
      ;;
    --strategy)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --strategy requires a value" >&2
        exit 2
      fi
      STRATEGY="$2"
      shift 2
      ;;
    --output-dir)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --output-dir requires a value" >&2
        exit 2
      fi
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --remote-url)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --remote-url requires a value" >&2
        exit 2
      fi
      REMOTE_URL="$2"
      shift 2
      ;;
    --include-working-tree)
      INCLUDE_WORKING_TREE=1
      shift
      ;;
    --skip-install)
      RUN_INSTALL=0
      shift
      ;;
    --skip-ci)
      RUN_CI=0
      shift
      ;;
    --cleanup)
      CLEANUP=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

bash "$ROOT_DIR/scripts/split_frontend_dry_run.sh" \
  --ref "$REF" \
  --strategy "$STRATEGY" \
  --output-dir "$OUTPUT_DIR" \
  $([[ "$INCLUDE_WORKING_TREE" -eq 1 ]] && printf '%s' '--include-working-tree') \
  $([[ "$RUN_INSTALL" -eq 0 ]] && printf '%s' '--skip-install') \
  $([[ "$RUN_CI" -eq 0 ]] && printf '%s' '--skip-ci')

if [[ -n "$REMOTE_URL" ]]; then
  git -C "$OUTPUT_DIR" remote remove origin >/dev/null 2>&1 || true
  git -C "$OUTPUT_DIR" remote add origin "$REMOTE_URL"
fi

echo
echo "Exported standalone frontend repo:"
echo "  path:     $OUTPUT_DIR"
echo "  strategy: $STRATEGY"
echo "  working-tree-overlay: $INCLUDE_WORKING_TREE"
echo "  cleanup:  $CLEANUP"
echo "  branch:   $(git -C "$OUTPUT_DIR" branch --show-current)"
echo "  head:     $(git -C "$OUTPUT_DIR" rev-parse --short HEAD)"

if [[ -n "$REMOTE_URL" ]]; then
  echo "  origin:   $REMOTE_URL"
fi

if [[ "$CLEANUP" -eq 1 ]]; then
  cleanup_path "$OUTPUT_DIR"
  if [[ -e "$OUTPUT_DIR" ]]; then
    echo "ERROR: cleanup failed: $OUTPUT_DIR" >&2
    exit 1
  fi
  echo "Cleaned up export: $OUTPUT_DIR"
fi
