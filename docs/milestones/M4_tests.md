# M4 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s` -> pass (`31 passed`).

## Coverage Status
- Added streak state-machine tests for transitions:
  - `S_NO_STREAK -> S_ACTIVE_TODAY`
  - `S_ACTIVE_TODAY -> S_AT_RISK`
  - `S_AT_RISK -> S_ACTIVE_TODAY`
  - `S_AT_RISK -> S_FROZEN_TODAY` (saver + premium)
  - `S_AT_RISK -> S_NO_STREAK`
  - `S_FROZEN_TODAY -> S_AT_RISK`
- Added tests for monthly premium freeze limit and season unlimited behavior.
- Added DST-aware Berlin date helper tests.

## Missing
- DB integration tests with row-level locking and concurrent activity events.
