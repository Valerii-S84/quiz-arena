# M5 Summary

## Implemented
- Integrated `/start` with DB-backed onboarding, energy sync, and streak sync.
- Added free-tier gameplay callback handlers:
  - `callback:play`
  - `callback:mode:<mode_code>`
  - `callback:daily_challenge`
  - `callback:answer:<session_id>:<option>`
- Implemented gameplay service (`GameSessionService`) with:
  - start flow with idempotency key support;
  - answer flow with idempotent replay handling;
  - `daily_challenge` one-per-day check;
  - locked mode check (premium/mode_access/free base access order);
  - energy debit exemption for zero-cost sources (`DAILY_CHALLENGE`, `FRIEND_CHALLENGE`, `TOURNAMENT`).
- Added home and quiz inline keyboards.
- Added static question bank for basic free-loop execution.

## Not Implemented
- Real question selection pipeline and anti-repeat constraints.
- Full offer/upsell routing for locked/empty-energy branches.
- Friend challenge flow and tournament entry handlers.

## Risks
- Static question bank is temporary and not production-ready for content scale.
- Callback idempotency is implemented via DB keys but not stress-tested under concurrent duplicated updates.

## Decisions
- Implemented M5 as functional vertical slice: user can run end-to-end free loop now.
- Kept question engine minimal to unblock handler integration with M3/M4 services.
