#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT_DIR"

resolve_python_bin() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if [[ "$PYTHON_BIN" == */* ]]; then
      if [[ -x "$PYTHON_BIN" ]]; then
        return
      fi
    elif command -v "$PYTHON_BIN" >/dev/null 2>&1; then
      return
    fi
    echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
    exit 1
  fi

  if [[ -x .venv/bin/python ]]; then
    PYTHON_BIN=.venv/bin/python
  elif [[ -x .venv/Scripts/python.exe ]]; then
    PYTHON_BIN=.venv/Scripts/python.exe
  else
    PYTHON_BIN=.venv/bin/python
  fi

  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "ERROR: Python venv not found at $PYTHON_BIN" >&2
    exit 1
  fi
}

resolve_python_bin

export APP_ENV=${APP_ENV:-test}
export LOG_LEVEL=${LOG_LEVEL:-INFO}
export TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-ci-test-token}
export TELEGRAM_WEBHOOK_SECRET=${TELEGRAM_WEBHOOK_SECRET:-ci-test-secret}
export ADMIN_PASSWORD_PLAIN=${ADMIN_PASSWORD_PLAIN:-ci-test-admin-password}
export ADMIN_JWT_SECRET=${ADMIN_JWT_SECRET:-ci-test-admin-jwt-secret}
export ADMIN_REFRESH_SECRET=${ADMIN_REFRESH_SECRET:-ci-test-admin-refresh-secret}
export INTERNAL_API_TOKEN=${INTERNAL_API_TOKEN:-ci-internal-token}
export PROMO_SECRET_PEPPER=${PROMO_SECRET_PEPPER:-ci-test-promo-pepper}
export PROMO_ENCRYPTION_KEY=${PROMO_ENCRYPTION_KEY:-MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY}
export TEST_DATABASE_URL=${TEST_DATABASE_URL:-postgresql+asyncpg://quiz:quiz@127.0.0.1:5432/quiz_arena_test_tournaments}
export DATABASE_URL=$TEST_DATABASE_URL
export REDIS_URL=${REDIS_URL:-redis://127.0.0.1:6379/10}
export CELERY_BROKER_URL=${CELERY_BROKER_URL:-redis://127.0.0.1:6379/11}
export CELERY_RESULT_BACKEND=${CELERY_RESULT_BACKEND:-redis://127.0.0.1:6379/12}
export TMPDIR=${TMPDIR:-/tmp}
export SKIP_LOCAL_SERVICES=${SKIP_LOCAL_SERVICES:-0}

UNIT_TESTS=(
  tests/game/test_daily_arena_golden.py
  tests/game/test_daily_arena_golden_extended_messaging.py
  tests/game/test_daily_arena_golden_extended_status.py
  tests/bot/test_daily_cup_flow.py
  tests/bot/test_daily_cup_keyboard.py
  tests/bot/test_daily_cup_menu_flow.py
  tests/bot/test_daily_cup_views.py
  tests/bot/test_friend_tournament_post_match_flow.py
  tests/bot/test_gameplay_daily_cup_handler.py
  tests/bot/test_gameplay_handler_flow_tournament.py
  tests/bot/test_gameplay_tournament_notifications.py
  tests/bot/test_gameplay_tournaments_more.py
  tests/bot/test_start_handler_flow_tournament.py
  tests/bot/test_tournament_keyboard.py
  tests/game/test_daily_arena_golden_extended_proof_cards.py
  tests/game/test_daily_cup_badge.py
  tests/game/test_daily_cup_deadline_progress.py
  tests/game/test_daily_cup_proof_cards_enqueue.py
  tests/game/test_daily_cup_question_levels.py
  tests/game/test_daily_cup_slots.py
  tests/game/test_private_tournament_proof_cards_enqueue.py
  tests/game/test_tournament_pairing.py
  tests/game/test_tournament_settlement.py
  tests/workers/test_daily_cup_match_results.py
  tests/workers/test_daily_cup_match_results_text.py
  tests/workers/test_daily_cup_messaging_followups.py
  tests/workers/test_daily_cup_messaging_text.py
  tests/workers/test_daily_cup_nonfinishers_summary.py
  tests/workers/test_daily_cup_prestart_reminder.py
  tests/workers/test_daily_cup_proof_cards_text.py
  tests/workers/test_daily_cup_schedule.py
  tests/workers/test_daily_cup_task.py
  tests/workers/test_daily_cup_turn_reminder_resolution.py
  tests/workers/test_daily_cup_turn_reminder_worker.py
  tests/workers/test_tournaments_messaging.py
  tests/workers/test_tournaments_messaging_text.py
  tests/workers/test_tournaments_proof_card_render.py
  tests/workers/test_tournaments_task.py
)

INTEGRATION_TESTS=(
  tests/integration/test_daily_arena_golden_integration.py
  tests/integration/test_daily_cup_nonfinishers_integration.py
  tests/integration/test_daily_cup_prestart_reminder_integration.py
  tests/integration/test_daily_cup_proof_cards_delivery_integration.py
  tests/integration/test_daily_cup_proof_cards_rewards_integration.py
  tests/integration/test_daily_cup_proof_cards_standings_integration.py
  tests/integration/test_daily_cup_question_levels_integration.py
  tests/integration/test_daily_cup_registration_push_integration.py
  tests/integration/test_daily_cup_round_deadline_progress_integration.py
  tests/integration/test_daily_cup_round_limits_integration.py
  tests/integration/test_daily_cup_round_messaging_integration.py
  tests/integration/test_daily_cup_rounds_race_integration.py
  tests/integration/test_daily_cup_self_bot_integration.py
  tests/integration/test_daily_cup_standings_integration.py
  tests/integration/test_daily_cup_uniform_questions.py
  tests/integration/test_daily_cup_worker_e2e_extended_integration.py
  tests/integration/test_daily_cup_worker_e2e_integration.py
  tests/integration/test_daily_cup_worker_integration.py
  tests/integration/test_private_tournament_service_integration.py
  tests/integration/test_private_tournament_worker_integration.py
  tests/integration/test_private_tournament_worker_proof_cards_integration.py
)

run_step() {
  local title=$1
  shift
  echo
  echo "==> ${title}"
  "$@"
}

assert_test_files_exist() {
  local path
  for path in "${UNIT_TESTS[@]}" "${INTEGRATION_TESTS[@]}"; do
    if [[ ! -f "$path" ]]; then
      echo "ERROR: expected tournament regression test file is missing: $path" >&2
      exit 1
    fi
  done
}

require_python_version() {
  "$PYTHON_BIN" - <<'PY'
import sys

expected = "3.12"
current = f"{sys.version_info.major}.{sys.version_info.minor}"
if current != expected:
    raise SystemExit(
        f"Tournament regression expects Python {expected}, but local venv uses {current}."
    )
PY
}

validate_test_db_safety() {
  "$PYTHON_BIN" - <<'PY'
import os

from app.core.integration_db_safety import assert_safe_integration_db, assess_integration_db_safety

database_url = os.environ["TEST_DATABASE_URL"]
assert_safe_integration_db(database_url)
result = assess_integration_db_safety(database_url)
print(f"Using safe TEST_DATABASE_URL database: {result.database_name} on host {result.host}")
PY
}

validate_test_redis_safety() {
  "$PYTHON_BIN" - <<'PY'
import os
from urllib.parse import urlparse

ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", "redis", "quiz_arena_redis"}
RESERVED_APP_DBS = {0, 1, 2}


def _redis_db_index(redis_url: str) -> int:
    parsed = urlparse(redis_url)
    path = parsed.path.lstrip("/")
    if not path:
        return 0
    try:
        return int(path)
    except ValueError as exc:
        raise RuntimeError(f"Redis URL path must be a database index: {redis_url}") from exc


def _validate_redis_url(env_name: str) -> int:
    redis_url = os.environ[env_name]
    parsed = urlparse(redis_url)
    host = (parsed.hostname or "").lower()
    db_index = _redis_db_index(redis_url)
    if parsed.scheme != "redis":
        raise RuntimeError(f"{env_name} must use redis:// for local tournament regression.")
    if host not in ALLOWED_HOSTS:
        raise RuntimeError(f"{env_name} host must be local/test-only, got: {host!r}")
    if db_index in RESERVED_APP_DBS:
        raise RuntimeError(
            f"{env_name} uses Redis DB {db_index}, reserved for normal app/test services. "
            "Use isolated tournament DBs, e.g. 10/11/12."
        )
    return db_index


resolved = {
    env_name: _validate_redis_url(env_name)
    for env_name in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND")
}
print(
    "Using isolated Redis DBs: "
    + ", ".join(f"{env_name}={db_index}" for env_name, db_index in resolved.items())
)
PY
}

prepare_test_db() {
  env DATABASE_URL="$TEST_DATABASE_URL" "$PYTHON_BIN" -m scripts.ensure_test_db
}

wait_for_local_services() {
  "$PYTHON_BIN" - <<'PY'
import asyncio
import os
import time

import asyncpg
from redis.asyncio import Redis
from sqlalchemy.engine import make_url


def _asyncpg_dsn(database_url: str) -> str:
    parsed = make_url(database_url)
    normalized = parsed.set(drivername="postgresql", database="postgres")
    return normalized.render_as_string(hide_password=False)


async def wait_for_postgres() -> None:
    deadline = time.monotonic() + 90
    last_error: Exception | None = None
    dsn = _asyncpg_dsn(os.environ["TEST_DATABASE_URL"])
    while time.monotonic() < deadline:
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            print("Postgres server is ready")
            return
        except Exception as exc:  # pragma: no cover - environment timing dependent
            last_error = exc
            await asyncio.sleep(2)
    raise RuntimeError(f"Postgres did not become ready in time: {last_error}")


async def wait_for_redis() -> None:
    deadline = time.monotonic() + 90
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        client = Redis.from_url(os.environ["REDIS_URL"])
        try:
            if await client.ping():
                print("Redis is ready")
                return
        except Exception as exc:  # pragma: no cover - environment timing dependent
            last_error = exc
        finally:
            await client.aclose()
        await asyncio.sleep(2)
    raise RuntimeError(f"Redis did not become ready in time: {last_error}")


async def main() -> None:
    await wait_for_postgres()
    await wait_for_redis()


asyncio.run(main())
PY
}

start_local_services() {
  local docker_bin
  if command -v docker >/dev/null 2>&1; then
    docker_bin=docker
  elif command -v docker.exe >/dev/null 2>&1; then
    docker_bin=docker.exe
  else
    echo "docker not found; assuming Postgres and Redis are already running"
    return
  fi
  "$docker_bin" compose up -d postgres redis
}

flush_test_redis_databases() {
  "$PYTHON_BIN" - <<'PY'
import asyncio
import os

from redis.asyncio import Redis


async def flush_once(redis_url: str, seen: set[str]) -> None:
    if redis_url in seen:
        return
    seen.add(redis_url)
    client = Redis.from_url(redis_url)
    try:
        await client.flushdb()
    finally:
        await client.aclose()


async def main() -> None:
    seen: set[str] = set()
    for env_name in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        await flush_once(os.environ[env_name], seen)
    print("Isolated Redis DBs flushed")


asyncio.run(main())
PY
}

run_unit_regression() {
  env DATABASE_URL="$TEST_DATABASE_URL" TMPDIR="$TMPDIR" \
    "$PYTHON_BIN" -m pytest -q "${UNIT_TESTS[@]}"
}

run_integration_regression() {
  env DATABASE_URL="$TEST_DATABASE_URL" TMPDIR="$TMPDIR" \
    "$PYTHON_BIN" -m pytest -q -s "${INTEGRATION_TESTS[@]}"
}

run_step "Validate tournament test inventory" assert_test_files_exist
run_step "Validate Python version" require_python_version
run_step "Validate TEST_DATABASE_URL safety" validate_test_db_safety
run_step "Validate Redis isolation" validate_test_redis_safety
if [[ "${SKIP_LOCAL_SERVICES}" == "1" ]]; then
  run_step "Wait for external Postgres and Redis" wait_for_local_services
else
  run_step "Start local Postgres and Redis" start_local_services
  run_step "Wait for Postgres and Redis" wait_for_local_services
fi
run_step "Ensure test database exists" prepare_test_db
run_step "Flush isolated Redis DBs" flush_test_redis_databases
run_step "Apply migrations" env DATABASE_URL="$TEST_DATABASE_URL" "$PYTHON_BIN" -m alembic upgrade head
run_step "Tournament regression (unit, bot, workers, game)" run_unit_regression
run_step "Tournament regression (integration)" run_integration_regression
