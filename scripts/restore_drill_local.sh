#!/usr/bin/env bash
set -euo pipefail

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-quiz_arena_postgres}"
POSTGRES_USER="${POSTGRES_USER:-quiz}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-quiz}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
DRILL_DB="${DRILL_DB:-quiz_arena_restore_drill}"
SEED_TELEGRAM_USER_ID="${SEED_TELEGRAM_USER_ID:-990000001}"
SEED_UPDATE_ID="${SEED_UPDATE_ID:-880000001}"
TIMESTAMP="${TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
DRILL_BACKUP_PATH="${DRILL_BACKUP_PATH:-reports/restore_drill_${TIMESTAMP}.dump}"
DRILL_RESULT_PATH="${DRILL_RESULT_PATH:-reports/restore_drill_result_${TIMESTAMP}.json}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

psql_exec() {
  local db_name="$1"
  local sql="$2"
  docker exec "${POSTGRES_CONTAINER}" sh -lc \
    "PGPASSWORD='${POSTGRES_PASSWORD}' psql -U '${POSTGRES_USER}' -d '${db_name}' -v ON_ERROR_STOP=1 -Atc \"${sql}\""
}

mkdir -p "$(dirname "${DRILL_BACKUP_PATH}")"
mkdir -p "$(dirname "${DRILL_RESULT_PATH}")"

log "restore_drill_start db=${DRILL_DB} container=${POSTGRES_CONTAINER}"

if ! docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}\$"; then
  echo "Postgres container '${POSTGRES_CONTAINER}' is not running." >&2
  exit 1
fi

log "drop_recreate_drill_db"
psql_exec postgres "DROP DATABASE IF EXISTS ${DRILL_DB};"
psql_exec postgres "CREATE DATABASE ${DRILL_DB};"

DRILL_DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${DRILL_DB}"
log "alembic_upgrade_head"
DATABASE_URL="${DRILL_DATABASE_URL}" .venv/bin/python -m alembic upgrade head

log "seed_test_data"
psql_exec "${DRILL_DB}" "INSERT INTO users (id, telegram_user_id, username, first_name, referral_code, status) VALUES (1, ${SEED_TELEGRAM_USER_ID}, 'restore_user', 'Restore', 'RESTORE01', 'ACTIVE');"
psql_exec "${DRILL_DB}" "INSERT INTO processed_updates (update_id, processed_at, status, processing_task_id) VALUES (${SEED_UPDATE_ID}, NOW(), 'DONE', 'restore-drill-task');"

before_users="$(psql_exec "${DRILL_DB}" "SELECT COUNT(*) FROM users;")"
before_updates="$(psql_exec "${DRILL_DB}" "SELECT COUNT(*) FROM processed_updates;")"
before_tables="$(psql_exec "${DRILL_DB}" "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")"
before_revision="$(psql_exec "${DRILL_DB}" "SELECT version_num FROM alembic_version LIMIT 1;")"
before_seed_user="$(psql_exec "${DRILL_DB}" "SELECT COUNT(*) FROM users WHERE telegram_user_id = ${SEED_TELEGRAM_USER_ID};")"
before_seed_update="$(psql_exec "${DRILL_DB}" "SELECT COUNT(*) FROM processed_updates WHERE update_id = ${SEED_UPDATE_ID};")"

log "backup_create path=${DRILL_BACKUP_PATH}"
docker exec "${POSTGRES_CONTAINER}" sh -lc \
  "PGPASSWORD='${POSTGRES_PASSWORD}' pg_dump -U '${POSTGRES_USER}' -d '${DRILL_DB}' -Fc -f /tmp/restore_drill.dump"
docker cp "${POSTGRES_CONTAINER}:/tmp/restore_drill.dump" "${DRILL_BACKUP_PATH}"
docker exec "${POSTGRES_CONTAINER}" rm -f /tmp/restore_drill.dump

backup_size_bytes="$(wc -c < "${DRILL_BACKUP_PATH}" | tr -d ' ')"

log "simulate_loss_drop_db"
psql_exec postgres "DROP DATABASE IF EXISTS ${DRILL_DB};"
psql_exec postgres "CREATE DATABASE ${DRILL_DB};"

log "restore_from_backup"
docker cp "${DRILL_BACKUP_PATH}" "${POSTGRES_CONTAINER}:/tmp/restore_drill.dump"
docker exec "${POSTGRES_CONTAINER}" sh -lc \
  "PGPASSWORD='${POSTGRES_PASSWORD}' pg_restore -U '${POSTGRES_USER}' -d '${DRILL_DB}' --clean --if-exists /tmp/restore_drill.dump"
docker exec "${POSTGRES_CONTAINER}" rm -f /tmp/restore_drill.dump

after_users="$(psql_exec "${DRILL_DB}" "SELECT COUNT(*) FROM users;")"
after_updates="$(psql_exec "${DRILL_DB}" "SELECT COUNT(*) FROM processed_updates;")"
after_tables="$(psql_exec "${DRILL_DB}" "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")"
after_revision="$(psql_exec "${DRILL_DB}" "SELECT version_num FROM alembic_version LIMIT 1;")"
after_seed_user="$(psql_exec "${DRILL_DB}" "SELECT COUNT(*) FROM users WHERE telegram_user_id = ${SEED_TELEGRAM_USER_ID};")"
after_seed_update="$(psql_exec "${DRILL_DB}" "SELECT COUNT(*) FROM processed_updates WHERE update_id = ${SEED_UPDATE_ID};")"

result="false"
if [[ "${before_users}" == "${after_users}" \
   && "${before_updates}" == "${after_updates}" \
   && "${before_tables}" == "${after_tables}" \
   && "${before_revision}" == "${after_revision}" \
   && "${before_seed_user}" == "1" \
   && "${after_seed_user}" == "1" \
   && "${before_seed_update}" == "1" \
   && "${after_seed_update}" == "1" ]]; then
  result="true"
fi

cat > "${DRILL_RESULT_PATH}" <<EOF
{
  "timestamp_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "drill_db": "${DRILL_DB}",
  "backup_file": "${DRILL_BACKUP_PATH}",
  "backup_size_bytes": ${backup_size_bytes},
  "before": {
    "users_count": ${before_users},
    "processed_updates_count": ${before_updates},
    "public_tables_count": ${before_tables},
    "alembic_version": "${before_revision}",
    "seed_user_present": ${before_seed_user},
    "seed_update_present": ${before_seed_update}
  },
  "after_restore": {
    "users_count": ${after_users},
    "processed_updates_count": ${after_updates},
    "public_tables_count": ${after_tables},
    "alembic_version": "${after_revision}",
    "seed_user_present": ${after_seed_user},
    "seed_update_present": ${after_seed_update}
  },
  "restore_success": ${result}
}
EOF

log "restore_drill_result path=${DRILL_RESULT_PATH} success=${result}"

if [[ "${result}" != "true" ]]; then
  echo "Restore drill failed. See ${DRILL_RESULT_PATH}" >&2
  exit 1
fi
