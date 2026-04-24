#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT_DIR"

REF=${REF:-main}
STRATEGY=${STRATEGY:-subtree}
OUTPUT_DIR=${OUTPUT_DIR:-"$ROOT_DIR/.tmp/frontend-split-dryrun"}
RUN_INSTALL=1
RUN_CI=1
CLEANUP=0
INCLUDE_WORKING_TREE=0
FILTER_REPO_TEMP_DIR=""

usage() {
  cat <<'USAGE'
Usage: scripts/split_frontend_dry_run.sh [options]

Creates a local standalone frontend repo from the current monorepo history
using `git subtree split` or `git-filter-repo`, then optionally runs frontend
validation inside it.

Options:
  --ref <git-ref>          Source ref for the split history (default: main)
  --strategy <name>        Extraction strategy: subtree | filter-repo
                           (default: subtree)
  --output-dir <path>      Output directory for the standalone repo
                           (default: .tmp/frontend-split-dryrun)
  --include-working-tree   Overlay the current frontend/ working tree onto the
                           exported repo after history extraction
  --skip-install           Skip `npm ci`
  --skip-ci                Skip `npm run ci`
  --cleanup                Remove the output directory after a successful run
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
      windows_output_dir=$(wslpath -w "$absolute_path")
      cmd.exe /c rmdir /s /q "$windows_output_dir" >/dev/null 2>&1 || true
    fi
  fi

  if [[ -e "$absolute_path" ]]; then
    rm -rf "$absolute_path"
  fi
}

cleanup_output_dir() {
  cleanup_path "$OUTPUT_DIR"
}

cleanup_filter_repo_temp_dir() {
  cleanup_path "$FILTER_REPO_TEMP_DIR"
}

on_exit() {
  cleanup_filter_repo_temp_dir
}

materialize_via_subtree() {
  echo "==> Building frontend-only history from $REF with git subtree split"
  split_commit=$(git subtree split --prefix=frontend "$REF")
  echo "Split commit: $split_commit"

  echo "==> Materializing standalone repo at $OUTPUT_DIR"
  git init --quiet --initial-branch=main "$OUTPUT_DIR"
  git -C "$OUTPUT_DIR" fetch --quiet "$ROOT_DIR/.git" "$split_commit"
  git -C "$OUTPUT_DIR" checkout --quiet -B main FETCH_HEAD
}

materialize_via_filter_repo() {
  local source_commit
  local mirror_dir

  if ! command -v git-filter-repo >/dev/null 2>&1; then
    echo "ERROR: git-filter-repo is required for --strategy filter-repo" >&2
    exit 1
  fi

  source_commit=$(git rev-parse "${REF}^{commit}")
  FILTER_REPO_TEMP_DIR=$(mktemp -d /tmp/quiz-arena-frontend-filterrepo-XXXXXX)
  mirror_dir="$FILTER_REPO_TEMP_DIR/repo.git"

  echo "==> Creating temporary mirror clone for git-filter-repo"
  git clone --mirror --quiet "$ROOT_DIR/.git" "$mirror_dir"

  if git --git-dir="$mirror_dir" for-each-ref --format='delete %(refname)' refs/heads refs/remotes refs/tags | \
    git --git-dir="$mirror_dir" update-ref --stdin; then
    :
  fi

  git --git-dir="$mirror_dir" update-ref refs/heads/main "$source_commit"
  git --git-dir="$mirror_dir" symbolic-ref HEAD refs/heads/main

  echo "==> Rewriting frontend history with git-filter-repo"
  (
    cd "$mirror_dir"
    git-filter-repo --force --subdirectory-filter frontend
  )

  echo "==> Cloning filtered standalone repo to $OUTPUT_DIR"
  git clone --quiet "$mirror_dir" "$OUTPUT_DIR"
  git -C "$OUTPUT_DIR" remote remove origin >/dev/null 2>&1 || true
}

ensure_frontend_tooling() {
  if [[ "$RUN_INSTALL" -eq 1 || "$RUN_CI" -eq 1 ]]; then
    if ! command -v node >/dev/null 2>&1; then
      echo "ERROR: node is required for standalone frontend validation" >&2
      exit 1
    fi
    if ! command -v npm >/dev/null 2>&1; then
      echo "ERROR: npm is required for standalone frontend validation" >&2
      exit 1
    fi
  fi
}

run_frontend_validation() {
  if [[ "$RUN_INSTALL" -eq 1 ]]; then
    echo "==> Running npm ci"
    (
      cd "$OUTPUT_DIR"
      npm ci
    )
  fi

  if [[ "$RUN_CI" -eq 1 ]]; then
    echo "==> Running npm run ci"
    (
      cd "$OUTPUT_DIR"
      npm run ci
    )
  fi
}

overlay_current_frontend_worktree() {
  if [[ "$INCLUDE_WORKING_TREE" -ne 1 ]]; then
    return 0
  fi

  if ! command -v rsync >/dev/null 2>&1; then
    echo "ERROR: rsync is required for --include-working-tree" >&2
    exit 1
  fi

  echo "==> Overlaying current frontend working tree onto exported repo"
  rsync -a --delete \
    --exclude '.git/' \
    --exclude 'node_modules/' \
    --exclude '.next/' \
    --exclude 'out/' \
    --exclude 'coverage/' \
    --exclude 'dist/' \
    --exclude '*.tsbuildinfo' \
    --filter='+ /.env.example' \
    --filter='+ /.env.production.example' \
    --filter='- /.env*' \
    "$ROOT_DIR/frontend/" "$OUTPUT_DIR/"
}

trap on_exit EXIT

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

if [[ "$RUN_CI" -eq 1 && "$RUN_INSTALL" -eq 0 ]]; then
  echo "ERROR: --skip-install cannot be combined with frontend CI" >&2
  exit 2
fi

if ! git rev-parse --verify "${REF}^{commit}" >/dev/null 2>&1; then
  echo "ERROR: git ref does not exist: $REF" >&2
  exit 1
fi

case "$STRATEGY" in
  subtree|filter-repo)
    ;;
  *)
    echo "ERROR: unsupported strategy: $STRATEGY" >&2
    exit 2
    ;;
esac

if [[ -n "$(git status --porcelain)" && "$INCLUDE_WORKING_TREE" -ne 1 ]]; then
  echo "WARN: worktree is dirty; dry-run uses committed state from $REF only." >&2
fi

if [[ -e "$OUTPUT_DIR" ]]; then
  echo "ERROR: output directory already exists: $OUTPUT_DIR" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_DIR")"

case "$STRATEGY" in
  subtree)
    materialize_via_subtree
    ;;
  filter-repo)
    materialize_via_filter_repo
    ;;
esac

overlay_current_frontend_worktree

echo "==> Checking exported frontend boundary"
bash "$ROOT_DIR/scripts/check_frontend_export_boundary.sh" "$OUTPUT_DIR"

ensure_frontend_tooling
run_frontend_validation

echo
echo "Standalone frontend repo is ready:"
echo "  path:   $OUTPUT_DIR"
echo "  strategy: $STRATEGY"
echo "  working-tree-overlay: $INCLUDE_WORKING_TREE"
echo "  branch: $(git -C "$OUTPUT_DIR" branch --show-current)"
echo "  head:   $(git -C "$OUTPUT_DIR" rev-parse --short HEAD)"

if [[ "$CLEANUP" -eq 1 ]]; then
  cleanup_output_dir
  if [[ -e "$OUTPUT_DIR" ]]; then
    echo "ERROR: cleanup failed: $OUTPUT_DIR" >&2
    exit 1
  fi
  echo "Cleaned up: $OUTPUT_DIR"
else
  echo "Cleanup: rm -rf \"$OUTPUT_DIR\""
fi
