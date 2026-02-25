#!/usr/bin/env bash
set -euo pipefail

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required" >&2
  exit 1
fi

if ! command -v ssh >/dev/null 2>&1; then
  echo "ssh is required" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  cat >&2 <<'USAGE'
Usage: scripts/deploy.sh <user@host> [remote_dir]

Example:
  scripts/deploy.sh root@203.0.113.10 /opt/quiz-arena
USAGE
  exit 1
fi

REMOTE="$1"
REMOTE_DIR="${2:-/opt/quiz-arena}"

echo "Deploy target: ${REMOTE}:${REMOTE_DIR}"

ssh "$REMOTE" "mkdir -p ${REMOTE_DIR}"

rsync -az --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '.env' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '.mypy_cache' \
  --exclude '.ruff_cache' \
  ./ "${REMOTE}:${REMOTE_DIR}/"

ssh "$REMOTE" "cd ${REMOTE_DIR} && \
  if [[ ! -f .env ]]; then cp .env.production.example .env; fi && \
  docker compose -f docker-compose.prod.yml up -d postgres redis && \
  docker compose -f docker-compose.prod.yml build api worker beat && \
  docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head && \
  docker compose -f docker-compose.prod.yml run --rm api sh -lc 'QUIZBANK_REPLACE_ALL_CONFIRM=PROD_REPLACE_ALL_OK QUIZBANK_REPLACE_ALL_CONFIRM_DB=\"\$POSTGRES_DB\" python -m scripts.quizbank_import_tool --replace-all' && \
  docker compose -f docker-compose.prod.yml run --rm api python -m scripts.quizbank_assert_non_empty && \
  docker compose -f docker-compose.prod.yml up -d --build api worker beat caddy && \
  docker compose -f docker-compose.prod.yml run --rm api python -m scripts.post_deploy_gate && \
  docker compose -f docker-compose.prod.yml ps"

echo "Deploy finished."
echo "Remember to configure .env secrets on server: ${REMOTE}:${REMOTE_DIR}/.env"
