# M1 DB Changes

## Migrations
- Added Alembic bootstrap config and revision:
  - `alembic.ini`
  - `alembic/env.py`
  - `alembic/versions/1c7257851be3_bootstrap_init.py`

## Schema Impact
- No schema objects created yet (empty bootstrap revision).

## Rollback
- Safe rollback: no-op, because no DDL executed.
