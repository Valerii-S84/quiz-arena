# M9 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_referrals_integration.py` -> pass (`7 passed`).
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/workers/test_referrals_task.py` -> pass (`2 passed`).
- `TMPDIR=/tmp .venv/bin/python -m pytest -q` -> pass (`130 passed`).

## Coverage Status
- Referral integration coverage includes:
  - deep-link referral start binding on new user;
  - duplicate `/start ref_<code>` replay for existing user keeps original referrer binding;
  - qualification logic (20 attempts / 14d / 2 local days);
  - 48h reward delay and 3-qualified threshold;
  - monthly cap (2 rewards/month) and deferred rollover;
  - canceled referral on deleted referred user;
  - velocity-based fraud rejection.
- Worker coverage includes:
  - Celery task wrapper execution for qualification and reward distribution jobs.

## Missing
- Telegram sandbox E2E scenario for `/start ref_<code>` -> qualification progression -> reward user notification flow.
- Concurrency stress tests for parallel referral qualification/reward job runs.
