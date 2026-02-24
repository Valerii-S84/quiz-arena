# P3 Production Resilience Report

Date: `2026-02-24`

Scope:
- automatic Postgres backups + rotation
- executed restore drill (local, reproducible)
- rerun of load/burst k6 profiles after latest optimizations

Constraints respected:
- no business-logic/UX changes
- only ops/config/docs/scripts/reports touched

## A) Postgres automatic backups

Implemented:
1. `docker-compose.prod.yml`
- new service: `postgres_backup`
- uses `scripts/postgres_backup.sh`
- full backup format: `pg_dump -Fc`
- schedule: `POSTGRES_BACKUP_INTERVAL_SECONDS` (default `86400`)
- retention: `POSTGRES_BACKUP_RETENTION_COUNT` (default `7`)
- backup volume: `pg_backups:/backups`

2. `scripts/postgres_backup.sh`
- atomic backup write: `*.tmp` -> `mv` to final dump name
- timestamped filename: `${PGDATABASE}_YYYYMMDDTHHMMSSZ.dump`
- rotation: keep latest `N`, delete older dumps
- modes:
  - `loop` (for prod service)
  - `--once` (manual verification)

Evidence (local verification run):
- backup log: `reports/p3_backup_run_2026-02-24.log`
- backup listing after rotation: `reports/p3_backup_check_2026-02-24.log`
- current retained files:
  - `quiz_arena_20260224T191304Z.dump`
  - `quiz_arena_20260224T193423Z.dump`

## B) Restore drill (executed)

Executed command:
```bash
POSTGRES_CONTAINER=quiz_arena_postgres \
POSTGRES_USER=quiz \
POSTGRES_PASSWORD=quiz \
POSTGRES_PORT=5432 \
DRILL_DB=quiz_arena_restore_drill \
scripts/restore_drill_local.sh
```

Artifacts:
- dump: `reports/restore_drill_20260224T191313Z.dump`
- drill result: `reports/restore_drill_result_20260224T191313Z.json`

Observed result (`restore_drill_result_20260224T191313Z.json`):
- `restore_success: true`
- `alembic_version`: `e7f8a9b0c1d2` before == after
- `users_count`: `1` before == after
- `processed_updates_count`: `1` before == after
- `public_tables_count`: `24` before == after
- seeded records restored (`seed_user_present=1`, `seed_update_present=1`)

Restore success criteria checklist:
- [x] backup dump created and non-empty
- [x] DB drop/recreate simulated
- [x] restore from dump succeeded
- [x] migration revision preserved
- [x] key seeded rows present after restore
- [x] table/row counts match before vs after

## C) k6 load/burst rerun

Execution target:
- API: local `app.main` on `http://127.0.0.1:8000`
- DB/Redis: local docker compose (`quiz_arena_postgres`, `quiz_arena_redis`)

Executed commands:
```bash
# Peak
.venv/bin/python -m scripts.pg_lock_waits_snapshot --database-url 'postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena' > reports/p3_resilience_peak_db_before_2026-02-24.json
docker run --rm --add-host=host.docker.internal:host-gateway \
  -e K6_PROFILE=peak -e BASE_URL=http://host.docker.internal:8000 -e WEBHOOK_SECRET=change_me_now \
  -v "$PWD/load/k6:/scripts:ro" -v "$PWD/reports:/reports" \
  grafana/k6 run /scripts/webhook_start_profiles.js --summary-export=/reports/k6_peak_summary_resilience_2026-02-24.json
.venv/bin/python -m scripts.pg_lock_waits_snapshot --database-url 'postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena' > reports/p3_resilience_peak_db_after_2026-02-24.json

# Burst
.venv/bin/python -m scripts.pg_lock_waits_snapshot --database-url 'postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena' > reports/p3_resilience_burst_db_before_2026-02-24.json
docker run --rm --add-host=host.docker.internal:host-gateway \
  -e K6_PROFILE=burst -e BASE_URL=http://host.docker.internal:8000 -e WEBHOOK_SECRET=change_me_now \
  -v "$PWD/load/k6:/scripts:ro" -v "$PWD/reports:/reports" \
  grafana/k6 run --quiet /scripts/webhook_start_profiles.js --summary-export=/reports/k6_burst_summary_resilience_2026-02-24.json
.venv/bin/python -m scripts.pg_lock_waits_snapshot --database-url 'postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena' > reports/p3_resilience_burst_db_after_2026-02-24.json
```

Gate artifacts:
- `reports/p3_resilience_peak_gate_2026-02-24.json`
- `reports/p3_resilience_burst_gate_2026-02-24.json`

Gate outcome:
- `peak`: PASS (`p95=6.447ms`, `error_rate=0.000596`, `db_lock_waits=0`, `deadlocks_delta=0`)
- `burst`: PASS (`p95=6.218ms`, `error_rate=0.0`, `db_lock_waits=0`, `deadlocks_delta=0`)

Comparison vs previous optimized baseline (`p2_3b`):
- comparison artifact: `reports/p3_resilience_k6_comparison_2026-02-24.json`

1. Peak:
- previous: `p95=5.637ms`, `error_rate=0.000000`, `iter_rate=47.435/s`
- current: `p95=6.447ms`, `error_rate=0.000596`, `iter_rate=49.206/s`
- delta: `+0.810ms p95`, `+0.000596 error`, `+1.771/s throughput`

2. Burst:
- previous: `p95=5.618ms`, `error_rate=0.000195`, `iter_rate=69.938/s`
- current: `p95=6.218ms`, `error_rate=0.000000`, `iter_rate=72.300/s`
- delta: `+0.600ms p95`, `-0.000195 error`, `+2.361/s throughput`

## Conclusion (new ceiling / bottleneck)

- New practical ceiling under current k6 profiles: stable handling up to burst profile rates with `p95 ~6ms` and near-zero failures.
- No DB lock/deadlock pressure observed (`lock_waits=0`, `deadlocks_delta=0`) during both peak and burst.
- Current bottleneck is not DB contention under tested profile; latency headroom remains high relative to SLO thresholds (350/500 ms).

## Production notes (placeholders)

No direct production server access in this slice; production rollout is documented with placeholders:
- `docs/runbooks/backups_and_restore_drill.md`
- replace `<SSH_USER>`, `<SERVER_HOST>`, `<DEPLOY_PATH>`, `<DUMP_FILE>` with real values.
