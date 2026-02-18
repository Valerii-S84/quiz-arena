# M7 DB Changes

## Migrations
- No new Alembic migrations in M7.

## Schema Impact
- None. Uses existing `entitlements`, `ledger_entries`, and `purchases` schema.

## Rollback
- No-op for DB schema (no DDL changed).

## Compatibility
- Fully compatible with M2-M6 schema and previous purchase flow.
