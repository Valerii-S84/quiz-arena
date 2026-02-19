# M9 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_referrals_integration.py` -> pass (`7 passed`).
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/workers/test_referrals_task.py` -> pass (`2 passed`).
- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/integration/test_internal_referrals_review_integration.py` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q` -> pass (`130 passed`).
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s tests/api/test_internal_referrals_auth.py tests/integration/test_internal_referrals_dashboard_integration.py tests/services/test_referrals_observability.py tests/workers/test_referrals_observability_task.py` -> pass (`7 passed`).

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
  - Celery task wrapper execution for referral fraud observability job.
- Observability coverage includes:
  - internal referral dashboard auth checks;
  - integration validation for funnel/fraud triage metrics;
  - threshold evaluation unit coverage for fraud-spike detection.
- Manual-review workflow coverage includes:
  - auth checks for triage endpoints;
  - review queue filtering;
  - decision transitions (`CONFIRM_FRAUD`, idempotent replay, `REOPEN`).

## Missing
- Telegram sandbox E2E scenario for `/start ref_<code>` -> qualification progression -> reward user notification flow.
- Concurrency stress tests for parallel referral qualification/reward job runs.
