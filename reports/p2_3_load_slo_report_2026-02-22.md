# P2-3 Load/Stress + SLO Gates Report

Date: `2026-02-22`

## P2-3b Re-Run After Webhook Enqueue Edge Fix

Patch scope:
- `app/api/routes/telegram_webhook.py`:
  - moved Celery enqueue to thread + timeout-bound fail-fast path for real Celery task objects;
  - keeps in-loop path for non-Celery test doubles to avoid coroutine-leak warnings in integration tests.
  - reliability invariant enforced: if enqueue fails/timeouts, webhook returns `503 {"status":"retry"}` (no 2xx acknowledgment).
- `app/core/config.py`:
  - added `TELEGRAM_WEBHOOK_ENQUEUE_TIMEOUT_MS` (default `250`).
- `.env.example`, `.env.production.example`:
  - added `TELEGRAM_WEBHOOK_ENQUEUE_TIMEOUT_MS=250`.
- tests:
  - `tests/api/test_telegram_webhook.py` extended with enqueue-failure and loop-bound fallback checks.

Executed post-fix validation:
- `ruff check app/api/routes/telegram_webhook.py app/core/config.py tests/api/test_telegram_webhook.py` -> passed
- `pytest -q tests/api/test_telegram_webhook.py` -> `6 passed`
- `pytest -q -s tests/integration/test_telegram_sandbox_smoke_integration.py::test_telegram_webhook_smoke_referral_reward_choice_duplicate_replay` -> `1 passed`

Post-fix load re-run artifacts:
- `reports/k6_peak_summary_p2_3b.json`
- `reports/k6_burst_summary_p2_3b.json`
- `reports/k6_duplicate_summary_p2_3b.json`
- `reports/p2_3b_peak_gate.json`
- `reports/p2_3b_burst_gate.json`
- `reports/p2_3b_duplicate_gate_observation.json`

Post-fix gate outcomes:
1. `peak` (SLO: p95 < 400ms, error < 1%):
   - p95: `5.637 ms`
   - error_rate: `0.000000`
   - db_lock_waits / deadlocks_delta: `0 / 0`
   - Gate: `PASS`
2. `burst` (SLO: p95 < 500ms, error < 1.5%):
   - p95: `5.618 ms`
   - error_rate: `0.000195`
   - db_lock_waits / deadlocks_delta: `0 / 0`
   - Gate: `PASS`
3. `duplicate`:
   - p95: `15.703 ms`
   - http_req_failed rate: `0.000000`
   - webhook_duplicate_fail_rate: `0.000000`
   - Gate status vs thresholds: `PASS`

Before/after delta on previously failing paths:
1. `burst`:
   - before: `p95=57012.297ms`, `error_rate=0.364543` -> FAIL
   - after: `p95=5.618ms`, `error_rate=0.000195` -> PASS
2. `duplicate`:
   - before: `webhook_duplicate_fail_rate=0.018010` -> FAIL
   - after: `webhook_duplicate_fail_rate=0.000000` -> PASS

## Delivered
1. k6 profiles:
   - `load/k6/webhook_start_profiles.js` (`steady`/`peak`/`burst`)
   - `load/k6/webhook_duplicate_updates.js` (duplicate-delivery ingress pressure)
2. Gate tooling:
   - `scripts/pg_lock_waits_snapshot.py`
   - `scripts/evaluate_slo_gate.py`
3. SLO gate documentation:
   - `docs/performance/p2_3_load_slo_gates.md`
4. At-least-once/idempotency integration check:
   - `tests/integration/test_telegram_updates_idempotency_integration.py`

## Local Execution Status
- `k6` host binary is not installed (`k6: command not found`), but profiles were executed locally via Docker image `grafana/k6`.
- Execution target:
  - API: local `uvicorn app.main:app` on `127.0.0.1:8000`
  - DB/Redis: local `docker compose` services (`postgres`, `redis`)
- All k6 profile summary artifacts were produced:
  - `reports/k6_steady_summary.json`
  - `reports/k6_peak_summary.json`
  - `reports/k6_burst_summary.json`
  - `reports/k6_duplicate_summary.json`
- DB snapshots were captured for all executed profiles:
  - `reports/p2_3_steady_db_before.json` / `reports/p2_3_steady_db_after.json`
  - `reports/p2_3_peak_db_before.json` / `reports/p2_3_peak_db_after.json`
  - `reports/p2_3_burst_db_before.json` / `reports/p2_3_burst_db_after.json`
  - `reports/p2_3_duplicate_db_before.json` / `reports/p2_3_duplicate_db_after.json`

## SLO Gate Results (webhook_start)
1. `steady`:
   - p95: `5.795 ms` (target `< 300 ms`) -> PASS
   - error_rate: `0.000000` (target `< 0.01`) -> PASS
   - db_lock_waits: `0` (target `<= 2`) -> PASS
   - deadlocks_delta: `0` (target `= 0`) -> PASS
   - Gate: `PASS` (`reports/p2_3_steady_gate.json`)
2. `peak`:
   - p95: `6.078 ms` (target `< 400 ms`) -> PASS
   - error_rate: `0.000000` (target `< 0.01`) -> PASS
   - db_lock_waits: `0` (target `<= 3`) -> PASS
   - deadlocks_delta: `0` (target `= 0`) -> PASS
   - Gate: `PASS` (`reports/p2_3_peak_gate.json`)
3. `burst`:
   - p95: `57012.297 ms` (target `< 500 ms`) -> FAIL
   - error_rate: `0.364543` (target `< 0.015`) -> FAIL
   - db_lock_waits: `0` (target `<= 5`) -> PASS
   - deadlocks_delta: `0` (target `= 0`) -> PASS
   - Gate: `FAIL` (`reports/p2_3_burst_gate.json`)

## Duplicate Delivery Profile (webhook_duplicates)
- p95: `47.448 ms` (k6 threshold `< 500 ms`) -> PASS
- `http_req_failed` rate: `0.009005` (k6 threshold `< 0.01`) -> PASS
- `webhook_duplicate_fail_rate`: `0.018010` (k6 threshold `< 0.01`) -> FAIL
- Artifact: `reports/p2_3_duplicate_gate_observation.json`

## Runtime Observations
1. `peak` reached generator saturation warning:
   - `Insufficient VUs, reached 240 active VUs and cannot initialize more`
   - `dropped_iterations=3167` in `reports/k6_peak_summary.json`
2. `burst` produced sustained request timeout waves to `/webhook/telegram` and severe dropped load:
   - `dropped_iterations=22520` in `reports/k6_burst_summary.json`
3. Post-burst period showed degraded duplicate-path reliability (`webhook_duplicate_fail_rate` above target), despite `http_req_failed` remaining below 1%.

## Tooling Note
- During execution, `scripts/evaluate_slo_gate.py` initially failed to parse current k6 summary format.
- Script was patched to support both:
  - legacy `metric.values` payload, and
  - current direct metric fields (`value`, `p(95)`, etc.).
- Updated file: `scripts/evaluate_slo_gate.py`

## Validation (Executed)
- `python -m alembic upgrade head` (local DB) -> passed
- `python -m scripts.evaluate_slo_gate ...` for `steady` -> passed
- `python -m scripts.evaluate_slo_gate ...` for `peak` -> passed
- `python -m scripts.evaluate_slo_gate ...` for `burst` -> fails with `SLO_FAIL` (expected from metric breach)
