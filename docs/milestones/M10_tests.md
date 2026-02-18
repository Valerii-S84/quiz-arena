# M10 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_internal_promo_redeem_integration.py` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_promo_maintenance_jobs_integration.py` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/workers/test_promo_maintenance_task.py` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q` -> pass (`94 passed`).

## Coverage Status
- Integration coverage includes:
  - redeem grant success;
  - redeem discount success + idempotent replay;
  - already-used conflict;
  - rate-limit block after repeated failures;
  - first-purchase-only segmentation rejection.
- Promo maintenance job coverage includes:
  - reservation expiry;
  - campaign rollover to `EXPIRED`/`DEPLETED`;
  - brute-force guard autopause on abusive hash.
- Worker wrapper tests cover promo Celery task entrypoints.

## Missing
- End-to-end bot + webhook + promo payment chain smoke in Telegram sandbox.
