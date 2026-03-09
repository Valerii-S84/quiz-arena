#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT_DIR"

BASE_REF=${BASE_REF:-origin/main}
CI_PYTHON=${CI_PYTHON:-3.12}

if [[ -n "${PYTHON_BIN:-}" ]]; then
  :
elif [[ -f .venv/bin/python ]]; then
  PYTHON_BIN=.venv/bin/python
elif [[ -f .venv/Scripts/python.exe ]]; then
  PYTHON_BIN=.venv/Scripts/python.exe
else
  PYTHON_BIN=.venv/bin/python
fi

if [[ ! -f "$PYTHON_BIN" ]]; then
  echo "ERROR: Python venv not found at $PYTHON_BIN" >&2
  exit 1
fi

export APP_ENV=${APP_ENV:-test}
export LOG_LEVEL=${LOG_LEVEL:-INFO}
export TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-ci-test-token}
export TELEGRAM_WEBHOOK_SECRET=${TELEGRAM_WEBHOOK_SECRET:-ci-test-secret}
export INTERNAL_API_TOKEN=${INTERNAL_API_TOKEN:-ci-internal-token}
export PROMO_SECRET_PEPPER=${PROMO_SECRET_PEPPER:-ci-test-promo-pepper}
export TEST_DATABASE_URL=${TEST_DATABASE_URL:-postgresql+asyncpg://quiz:quiz@127.0.0.1:5432/quiz_arena_test}
export DATABASE_URL=${DATABASE_URL:-$TEST_DATABASE_URL}
export REDIS_URL=${REDIS_URL:-redis://127.0.0.1:6379/0}
export CELERY_BROKER_URL=${CELERY_BROKER_URL:-redis://127.0.0.1:6379/1}
export CELERY_RESULT_BACKEND=${CELERY_RESULT_BACKEND:-redis://127.0.0.1:6379/2}
export TMPDIR=${TMPDIR:-/tmp}

run_step() {
  local title=$1
  shift
  echo
  echo "==> ${title}"
  "$@"
}

lockfile_check() {
  tmp_req=$(mktemp)
  tmp_dev=$(mktemp)
  trap 'rm -f "$tmp_req" "$tmp_dev"' RETURN
  cp requirements.lock "$tmp_req"
  cp requirements-dev.lock "$tmp_dev"
  "$PYTHON_BIN" -m piptools compile --strip-extras pyproject.toml --output-file requirements.lock
  "$PYTHON_BIN" -m piptools compile --strip-extras --extra dev pyproject.toml --output-file requirements-dev.lock
  diff -u "$tmp_req" requirements.lock
  diff -u "$tmp_dev" requirements-dev.lock
}

require_ci_python_version() {
  "$PYTHON_BIN" - "$CI_PYTHON" <<'PY'
import sys

expected = sys.argv[1]
current = f"{sys.version_info.major}.{sys.version_info.minor}"
if current != expected:
    raise SystemExit(
        f"GitHub lint_unit uses Python {expected}, but local venv uses {current}. "
        "Recreate .venv with Python 3.12 to reproduce lockfile and lint behavior 1:1."
    )
PY
}

architecture_guards() {
  env CI=1 FORCE_GROWTH_CHECK=1 BASE_REF="$BASE_REF" bash -lc '
    bash scripts/check_line_limits.sh
    bash scripts/check_growth_delta.sh
    bash scripts/check_monolith_pattern.sh
    bash scripts/check_no_print_app.sh
    bash scripts/check_no_except_exception_pass.sh
    bash scripts/check_architecture_imports.sh
    bash scripts/check_import_cycles.sh
  '
}

run_step "Validate Python version" require_ci_python_version
run_step "Verify lockfiles are in sync with pyproject" lockfile_check

run_step "Verify QuizBank reports freshness" "$PYTHON_BIN" scripts/quizbank_reports.py check

run_step "Validate TEST_DATABASE_URL safety" "$PYTHON_BIN" - <<'PY'
import os
from sqlalchemy.engine import make_url

db_name = (make_url(os.environ["TEST_DATABASE_URL"]).database or "").strip()
if "test" not in db_name.lower():
    raise SystemExit(f"TEST_DATABASE_URL DB name must contain 'test', got: {db_name!r}")
print(f"Using safe TEST_DATABASE_URL database: {db_name}")
PY

run_step "Architecture guards" architecture_guards
run_step "Ruff" "$PYTHON_BIN" -m ruff check app tests
run_step "Black" "$PYTHON_BIN" -m black --check app tests
run_step "isort" "$PYTHON_BIN" -m isort --check-only app tests
run_step "Mypy" "$PYTHON_BIN" -m mypy app tests
run_step "Pytest (unit and bot)" env DATABASE_URL="$TEST_DATABASE_URL" TMPDIR="$TMPDIR" "$PYTHON_BIN" -m pytest -q --ignore=tests/integration
