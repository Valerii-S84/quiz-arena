# M10 DB Changes

## Migrations
- No new Alembic migrations in this M10 slice.

## Schema Impact
- None. Reuses existing promo tables:
  - `promo_codes`
  - `promo_redemptions`
  - `promo_attempts`
  - plus existing `entitlements` and `ledger_entries`.

## Rollback
- No-op for DB schema (no DDL changed).

## Compatibility
- Fully compatible with M2+ schema and previous purchase/payment flows.
