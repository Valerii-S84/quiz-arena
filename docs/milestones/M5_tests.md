# M5 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s` -> pass (`42 passed`).

## Coverage Status
- Added unit tests for mode access and zero-cost source rules.
- Existing suites for energy and streak state machines remain green.

## Missing
- Integration tests for callback handlers against a real DB transaction layer.
- End-to-end tests for duplicate callback update handling.
