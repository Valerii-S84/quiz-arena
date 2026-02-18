# NEXT_AGENT_BRIEF

## Current State
- M1-M5 completed (foundation, schema, energy, streak, free-loop gameplay).
- M6 completed beyond slice 1:
  - webhook endpoint + async update queue (`/webhook/telegram`);
  - payment recovery + reconciliation jobs;
  - anti-repeat question selection and persisted `question_id`;
  - Postgres integration tests for idempotent payment credit replay;
  - promo discount settlement in purchase flow.
- M7 completed:
  - all 4 premium plans in catalog;
  - premium entitlement grant on payment;
  - upgrade extension behavior + downgrade block.
- M10 core promo module is now implemented:
  - `POST /internal/promo/redeem` (`PREMIUM_GRANT`, `PERCENT_DISCOUNT`);
  - promo anti-abuse throttling (per-user + global brute-force autopause);
  - promo maintenance jobs (reservation expiry, campaign rollover, brute-force guard);
  - bot-level promo UX (`/promo <code>`, `promo:open`).
- Technical spec source of truth: `TECHNICAL_SPEC_ENERGY_STARS_BOT.md`.

## Critical Notes
- `.env` is local-only and must never be committed.
- Bot token is already configured locally; rotate token before production webhook go-live.
- Docker services are available in this runtime (`postgres`, `redis`) and currently running.
- Latest full validation run in this branch: `94 passed`.

## Immediate Next Steps (Priority)
1. Milestone 8: implement offer trigger engine + `offers_impressions` idempotent logging and caps.
2. Milestone 9: implement referral qualification + anti-fraud checks and reward flow.
3. M10 remaining hardening:
  - promo code generation/import tooling (batch/admin path),
  - targeted concurrency tests for parallel redeem collisions.
4. Add Telegram sandbox end-to-end smoke for webhook -> payment -> promo flows.

## Validation Commands
- `TMPDIR=/tmp .venv/bin/python -m pytest -q`
- `.venv/bin/ruff check app tests alembic scripts`
- `TMPDIR=/tmp .venv/bin/alembic heads`
