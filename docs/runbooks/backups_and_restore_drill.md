# Postgres Backups and Restore Drill

Date: `2026-02-24`

## 1) Production backup automation

Backup automation is configured in `docker-compose.prod.yml` via service `postgres_backup`:
- image: `postgres:16-alpine`
- schedule: every `POSTGRES_BACKUP_INTERVAL_SECONDS` (default `86400` = daily)
- retention: `POSTGRES_BACKUP_RETENTION_COUNT` (default `7`)
- storage volume: `pg_backups:/backups`
- script: `scripts/postgres_backup.sh`

Backup file format:
- full dump (`pg_dump -Fc`)
- filename: `${POSTGRES_DB}_YYYYMMDDTHHMMSSZ.dump`
- atomic write: dump to `*.tmp`, then `mv` to final name

## 2) How to verify backups are created (prod)

`<SERVER_HOST>` and `<DEPLOY_PATH>` are placeholders.

1. Deploy/update stack:
```bash
ssh <SSH_USER>@<SERVER_HOST> "cd <DEPLOY_PATH> && docker compose -f docker-compose.prod.yml up -d postgres postgres_backup"
```

2. Check backup service logs:
```bash
ssh <SSH_USER>@<SERVER_HOST> "cd <DEPLOY_PATH> && docker compose -f docker-compose.prod.yml logs --since=24h postgres_backup"
```

3. Verify backup files inside backup volume:
```bash
ssh <SSH_USER>@<SERVER_HOST> "docker run --rm -v <DEPLOY_PATH>_pg_backups:/backups alpine:3.20 ls -lah /backups"
```

4. Verify retention (last N files only):
```bash
ssh <SSH_USER>@<SERVER_HOST> "docker run --rm -v <DEPLOY_PATH>_pg_backups:/backups alpine:3.20 sh -lc 'ls -1 /backups/*.dump | wc -l'"
```

## 3) Local restore drill (executed flow)

Script: `scripts/restore_drill_local.sh`

Executed command:
```bash
POSTGRES_CONTAINER=quiz_arena_postgres \
POSTGRES_USER=quiz \
POSTGRES_PASSWORD=quiz \
POSTGRES_PORT=5432 \
DRILL_DB=quiz_arena_restore_drill \
scripts/restore_drill_local.sh
```

What the script does:
1. Drops/recreates drill DB.
2. Applies Alembic migrations (`upgrade head`).
3. Seeds test records into `users` and `processed_updates`.
4. Creates full backup dump.
5. Simulates data loss (drop/recreate DB).
6. Restores DB from dump with `pg_restore`.
7. Verifies schema version + seeded data + row counts before/after.
8. Writes JSON result to `reports/restore_drill_result_<timestamp>.json`.

## 4) Restore success criteria

Restore drill is considered successful only if all checks pass:
- `restore_success == true` in drill JSON result.
- `alembic_version` before restore equals after restore.
- `users` row count before restore equals after restore.
- `processed_updates` row count before restore equals after restore.
- seeded `telegram_user_id` is present after restore.
- seeded `update_id` is present after restore.

## 5) Manual restore command (prod emergency)

`<DUMP_FILE>` is a placeholder path in backup volume.

```bash
ssh <SSH_USER>@<SERVER_HOST> "
  cd <DEPLOY_PATH> && \
  docker compose -f docker-compose.prod.yml exec -T postgres \
    sh -lc 'PGPASSWORD=\"${POSTGRES_PASSWORD}\" pg_restore -U \"${POSTGRES_USER}\" -d \"${POSTGRES_DB}\" --clean --if-exists <DUMP_FILE>'
"
```

After restore, run DB smoke checks:
```bash
ssh <SSH_USER>@<SERVER_HOST> "
  cd <DEPLOY_PATH> && \
  docker compose -f docker-compose.prod.yml exec -T postgres \
    sh -lc 'PGPASSWORD=\"${POSTGRES_PASSWORD}\" psql -U \"${POSTGRES_USER}\" -d \"${POSTGRES_DB}\" -c \"SELECT version_num FROM alembic_version;\"'
"
```
