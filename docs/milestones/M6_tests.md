# M6 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s` -> pass (`44 passed`).

## Coverage Status
- Added product catalog tests.
- Existing gameplay, energy, and streak test suites remain green.

## Missing
- Integration tests for payment handler flow with real Postgres transactions.
- Idempotency and duplicate-payment replay integration tests.
