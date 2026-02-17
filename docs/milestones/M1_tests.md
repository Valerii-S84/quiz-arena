# M1 Tests

## Executed
- `ruff check app tests alembic scripts` -> pass.
- `pytest -q -s` -> pass (`2 passed`).

## Coverage Status
- Only bootstrap tests for health endpoints.
- Domain state-machine coverage is not implemented yet.
