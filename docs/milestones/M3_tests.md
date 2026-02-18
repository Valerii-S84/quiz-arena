# M3 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s` -> pass (`20 passed`).

## Coverage Status
- Added unit tests for energy state transitions and edge cases:
  - consume transitions
  - regen transitions
  - daily top-up behavior
  - premium on/off classification
  - no-negative-energy guarantee
  - Berlin local date boundary behavior

## Missing
- DB integration tests for transaction/idempotency under concurrent load.
