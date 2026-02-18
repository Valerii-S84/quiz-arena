# M5 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s` -> pass (`33 passed`).

## Coverage Status
- Added unit tests for referral-code generator.
- Existing energy/streak suites remain green.

## Missing
- Integration tests for `/start` onboarding flow with async DB session.
- End-to-end bot handler tests for free gameplay loop.
