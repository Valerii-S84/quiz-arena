# P2-3 Load/Stress + SLO Gates Report

Date: `2026-02-22`

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
- `k6` binary is not installed in this environment (`k6: command not found`), so load profiles were not executed locally.
- Integration idempotency test was executed and passed (see validation section).

## Validation (Executed)
- `ruff check app tests scripts` -> passed
- `pytest -q -s tests/integration/test_telegram_updates_idempotency_integration.py` -> passed

## Next Execution on Staging/Prod-like Environment
1. Install `k6`.
2. Run `steady`, `peak`, `burst` profiles with summary export.
3. Capture DB snapshots before/after each run.
4. Evaluate each run with `scripts/evaluate_slo_gate.py`.
5. Record PASS/FAIL per profile in this report.
