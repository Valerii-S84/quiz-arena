#!/usr/bin/env sh
set -eu

MODE="${1:-loop}"

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETENTION_COUNT="${BACKUP_RETENTION_COUNT:-7}"
BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"

PGHOST="${PGHOST:-postgres}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:?PGDATABASE is required}"
PGUSER="${PGUSER:?PGUSER is required}"
PGPASSWORD="${PGPASSWORD:?PGPASSWORD is required}"
export PGPASSWORD

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

rotate_backups() {
  all_backups="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name "${PGDATABASE}_*.dump" | sort -r)"
  old_backups="$(printf '%s\n' "$all_backups" | awk "NR>${BACKUP_RETENTION_COUNT}")"

  if [ -n "$old_backups" ]; then
    printf '%s\n' "$old_backups" | while IFS= read -r old_file; do
      [ -n "$old_file" ] || continue
      rm -f "$old_file"
      log "backup_deleted=${old_file}"
    done
  fi
}

run_backup_once() {
  mkdir -p "$BACKUP_DIR"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  final_file="${BACKUP_DIR}/${PGDATABASE}_${timestamp}.dump"
  tmp_file="${BACKUP_DIR}/.${PGDATABASE}_${timestamp}.dump.tmp"

  log "backup_start db=${PGDATABASE} host=${PGHOST}:${PGPORT} output=${final_file}"
  pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Fc -f "$tmp_file"
  mv "$tmp_file" "$final_file"
  log "backup_created=${final_file}"

  rotate_backups
}

case "$MODE" in
  --once)
    run_backup_once
    ;;
  loop)
    while true; do
      run_backup_once
      log "sleep_seconds=${BACKUP_INTERVAL_SECONDS}"
      sleep "$BACKUP_INTERVAL_SECONDS"
    done
    ;;
  *)
    echo "Usage: postgres_backup.sh [--once|loop]" >&2
    exit 1
    ;;
esac
