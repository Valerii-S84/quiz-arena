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
- Additional hardening completed in this session:
  - internal endpoint auth for promo redeem (`X-Internal-Token` + IP allowlist);
  - single active invoice lock per `(user_id, product_code)` (service + DB partial unique index);
  - `STREAK_SAVER_20` purchase limit enforced (once per 7 days);
  - payments reliability upgrades:
    - stale unpaid invoices (`CREATED`/`INVOICE_SENT`) auto-expire to `FAILED`;
    - reconciliation compares counts + stars totals + product-level stars drift;
    - generic ops webhook alerts on reconciliation diff and recovery review-required;
  - daily challenge DB uniqueness guarantee (one per user per Berlin day);
  - promo hardening:
    - parallel redeem collision integration test;
    - promo batch generation/import CLI (`scripts/promo_batch_tool.py`);
    - generic ops alert webhook for promo autopause events.
- Technical spec source of truth: `TECHNICAL_SPEC_ENERGY_STARS_BOT.md`.

## Critical Notes
- `.env` is local-only and must never be committed.
- Bot token is already configured locally; rotate token before production webhook go-live.
- Docker services are available in this runtime (`postgres`, `redis`) and currently running.
- Latest full validation run in this branch: `114 passed`.
- Current Alembic head: `f6a7b8c9d0e1`.

## Immediate Next Steps (Priority)
1. Milestone 8: implement offer trigger engine + `offers_impressions` idempotent logging and caps.
2. Milestone 9: implement referral qualification + anti-fraud checks and reward flow.
3. M10/M11 remaining hardening:
  - provider-specific alert routing (PagerDuty/Slack templates + escalation policy),
  - Telegram sandbox smoke for promo redeem -> purchase flow.
4. Add Telegram sandbox end-to-end smoke for webhook -> payment -> promo flows.

## Validation Commands
- `TMPDIR=/tmp .venv/bin/python -m pytest -q`
- `.venv/bin/ruff check app tests alembic scripts`
- `TMPDIR=/tmp .venv/bin/alembic heads`
