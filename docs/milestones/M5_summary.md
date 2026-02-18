# M5 Summary (Phase 1)

## Implemented
- Integrated `/start` handler with DB-backed onboarding flow.
- Added onboarding service `UserOnboardingService`:
  - finds/creates user by `telegram_user_id`;
  - generates unique referral code;
  - initializes/syncs M3 energy state;
  - initializes/syncs M4 streak state;
  - updates `last_seen_at`.
- Added German home response with live values:
  - title
  - energy line
  - streak line.
- Added referral-code utility + tests.

## Not Implemented
- Full free gameplay loop (question start/answer flow, locked checks, daily challenge exemptions).
- Callback keyboards and mode-selection navigation.
- Handler-level idempotency for gameplay callbacks.

## Risks
- `/start` path now depends on DB availability; no graceful degraded mode for DB outage.
- Onboarding flow is not yet covered by integration tests with real DB runtime.

## Decisions
- Chose incremental M5 delivery: first wire domain services to real handler entrypoint, then add gameplay handlers.
