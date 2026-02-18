# M2 Summary

## Implemented
- Added full SQLAlchemy ORM model set for all required tables from spec section 6.
- Added Alembic migration chain for complete schema rollout:
  - `2f4a1d9c0e11` (users, energy_state, streak_state, purchases)
  - `4e5f6a7b8c90` (ledger_entries, entitlements, mode_access)
  - `8b7c6d5e4f32` (quiz_sessions, quiz_attempts, offers_impressions, promo_codes, purchases->promo_codes FK)
  - `9a0b1c2d3e4f` (promo_redemptions, promo_attempts, referrals)
  - `c1d2e3f4a5b6` (processed_updates, outbox_events, reconciliation_runs, promo_code_batches)
- Added base async repositories for core entities (`users`, `energy`, `streak`, `purchases`, `promo`).
- Added metadata tests for table registration and critical constraints/indexes.

## Not Implemented
- Domain engines (energy/streak/purchase workflows) and transactional business logic.
- Runtime migration rehearsal with real Postgres `upgrade/downgrade` cycle.
- Integration tests for DB-level behavior.

## Risks
- Migration `up/down` against live Postgres is not verified in this WSL runtime (DB not available).
- Schema fidelity is validated at metadata/lint/test level, but not with lock/load rehearsal yet.

## Decisions
- Migration chain split into small revisions to keep file-size hard limit and rollback clarity.
- Partial unique premium constraint implemented via PostgreSQL partial index.
