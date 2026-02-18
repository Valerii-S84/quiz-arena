# M2 Tests

## Executed
- `.venv/bin/ruff check app tests alembic scripts` -> pass.
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s` -> pass (`4 passed`).
- `TMPDIR=/tmp .venv/bin/alembic heads` -> pass (`c1d2e3f4a5b6 (head)`).

## Coverage Status
- Added metadata-level assertions for table presence and critical constraints/indexes.
- DB integration checks (`alembic upgrade/downgrade` on Postgres) not executed due unavailable local DB runtime.
