# M9 DB Changes

## Migrations
- No new Alembic migration in this M9 slice.

## Schema Impact
- None (DDL unchanged).
- Reused existing `referrals` table and existing economy/game tables.
- Added application-level repository/query support only:
  - `app/db/repo/referrals_repo.py`
  - `app/db/repo/quiz_attempts_repo.py` (qualification counters)
  - `app/db/repo/mode_access_repo.py` (idempotency lookup for referral rewards)

## Rollback
- No-op for schema rollback (no DDL changes).
- Code rollback can be done by reverting referral service/workers/handler integration.

## Compatibility
- Compatible with current head (`f6a7b8c9d0e1`) and previous M1-M8/M10 flows.
