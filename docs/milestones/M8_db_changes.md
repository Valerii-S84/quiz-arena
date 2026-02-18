# M8 DB Changes

## Migrations
- No new Alembic migration in this M8 slice.

## Schema Impact
- None. Reused existing M2 table `offers_impressions` and existing purchase/entitlement tables.
- Added only repository/query layer changes in application code:
  - `app/db/repo/offers_repo.py`
  - `app/db/repo/purchases_repo.py` (windowed paid product count)
  - `app/db/repo/entitlements_repo.py` (starter-expired and month-expiring checks)

## Rollback
- No-op for schema rollback (no DDL changed).
- Application rollback is code-only: remove M8 offer service/handlers and revert bot integration.

## Compatibility
- Fully compatible with current Alembic head (`f6a7b8c9d0e1`) and prior M1-M7/M10 flows.
