# P2-3 Load/Stress + SLO Gates

## Scope
- k6 profiles for `steady`, `peak`, `burst` load on `POST /webhook/telegram` (`/start` ingress flow).
- Separate duplicate-delivery profile for at-least-once ingress pressure.
- Explicit SLO gate checks for:
  - `p95` latency for webhook/start
  - error rate
  - DB lock waits
  - deadlocks delta

## k6 Profiles
- `load/k6/webhook_start_profiles.js`
  - `K6_PROFILE=steady`
  - `K6_PROFILE=peak`
  - `K6_PROFILE=burst`
- `load/k6/webhook_duplicate_updates.js`
  - duplicate update delivery pressure (`same update_id` sent twice per iteration)

## Gate Thresholds
- `steady`:
  - `p95(webhook_start) < 300ms`
  - `error_rate < 1%`
  - `db_lock_waits <= 2`
  - `deadlocks_delta == 0`
- `peak`:
  - `p95(webhook_start) < 400ms`
  - `error_rate < 1%`
  - `db_lock_waits <= 3`
  - `deadlocks_delta == 0`
- `burst`:
  - `p95(webhook_start) < 500ms`
  - `error_rate < 1.5%`
  - `db_lock_waits <= 5`
  - `deadlocks_delta == 0`

## Runbook Commands
1. Snapshot DB lock/deadlock baseline:
```bash
.venv/bin/python -m scripts.pg_lock_waits_snapshot --database-url "$DATABASE_URL"
```

2. Run k6 profile with summary export:
```bash
K6_PROFILE=steady \
BASE_URL=http://127.0.0.1:8000 \
WEBHOOK_SECRET=replace_me \
k6 run load/k6/webhook_start_profiles.js --summary-export=reports/k6_steady_summary.json
```

3. Snapshot DB after run and compute `deadlocks_delta`:
```bash
.venv/bin/python -m scripts.pg_lock_waits_snapshot --database-url "$DATABASE_URL"
```

4. Evaluate SLO gate:
```bash
.venv/bin/python -m scripts.evaluate_slo_gate \
  --summary-file reports/k6_steady_summary.json \
  --flow-tag webhook_start \
  --max-p95-ms 300 \
  --max-error-rate 0.01 \
  --db-lock-waits 2 \
  --max-db-lock-waits 2 \
  --deadlocks-delta 0 \
  --max-deadlocks-delta 0
```

## At-Least-Once + Idempotency Validation
- Integration check (required):
```bash
DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test \
TMPDIR=/tmp .venv/bin/python -m pytest -q -s tests/integration/test_telegram_updates_idempotency_integration.py
```
- Optional ingress duplicate profile:
```bash
BASE_URL=http://127.0.0.1:8000 \
WEBHOOK_SECRET=replace_me \
k6 run load/k6/webhook_duplicate_updates.js --summary-export=reports/k6_duplicate_summary.json
```
