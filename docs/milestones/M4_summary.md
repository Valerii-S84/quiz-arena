# M4 Summary

## Implemented
- Added streak domain module `app/economy/streak/` with:
  - Berlin-local day and week helpers (DST-safe by timezone conversion).
  - Streak state machine rules for rollover, day-end freeze policy, and activity counting.
  - Premium freeze policy:
    - Starter: no premium freeze.
    - Month: max 1 premium freeze per Berlin week.
    - Season/Year: unlimited premium freezes.
  - Service orchestration for:
    - `sync_rollover`
    - `record_activity`
- Extended entitlements repository with active premium scope resolution for streak policy.
- Added full unit test suite for streak transitions and timezone edge cases.

## Not Implemented
- Handler/webhook integration for runtime streak events.
- Integration tests on real Postgres with concurrent updates.
- Explicit streak-saver purchase 7-day purchase-limit enforcement (purchase-layer concern).

## Risks
- Multi-node scheduler concurrency is not yet load-tested on production-like DB runtime.
- Premium scope naming must stay consistent with purchase entitlement writer.

## Decisions
- Kept streak transition logic pure and deterministic in `rules.py`.
- Used `updated_at` as the processed-day anchor for multi-day rollover catch-up.
