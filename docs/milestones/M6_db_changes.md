# M6 DB Changes

## Migrations
- No new Alembic migrations in M6 slice 1.

## Schema Impact
- None. Uses M2 schema (`purchases`, `ledger_entries`, `mode_access`, `streak_state`).

## Rollback
- No-op for DB schema (no DDL changed).

## Compatibility
- Fully compatible with existing M2/M3/M4/M5 schema and services.
