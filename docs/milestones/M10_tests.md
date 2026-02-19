# M10 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_internal_promo_redeem_integration.py` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_internal_promo_admin_integration.py` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_promo_maintenance_jobs_integration.py` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_payments_idempotency_integration.py::test_refund_promo_rollback_job_revokes_discount_redemption_without_decrementing_usage` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/workers/test_promo_maintenance_task.py` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/workers/test_payments_reliability_task.py` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_telegram_sandbox_smoke_integration.py` -> pass.
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
- Promo admin integration coverage includes:
  - campaign status mutation and listing;
  - forbidden unsafe unpause from `DEPLETED`;
  - refund rollback idempotency and `REVOKED` status.
- Payments reliability integration coverage includes:
  - periodic refund-driven promo rollback (`PR_REVOKED`);
  - invariant that `promo_codes.used_total` is not decremented on refund rollback.
- Worker wrapper tests cover promo/payments reliability Celery task entrypoints.
- Telegram webhook E2E smoke coverage includes:
  - `/promo <code>` discount redeem -> `buy` callback with promo reservation -> pre-checkout -> successful payment -> credit;
  - referral reward choice callback claim and duplicate callback replay safety.

## Missing
- Dedicated external Telegram sandbox runbook (real Bot API + Stars payment provider) on top of local webhook smoke automation.
- Standalone visual admin UI for promo operations (API workflow endpoints are available).
