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
- M8 completed:
  - offer trigger engine with deterministic priority resolver;
  - anti-spam caps (6h blocking modal, 3/day, same offer 24h, mute 72h);
  - idempotent `offers_impressions` logging and bot offer surfaces (`/start`, locked mode, energy empty);
  - offer dismiss callback flow (`offer:dismiss:<impression_id>`).
- M9 completed:
  - referral start tracking via `/start ref_<code>` onboarding payload;
  - referral qualification checks (20 attempts / 14d / 2 local days);
  - anti-fraud guards (cyclic pair + velocity limit);
  - reward distribution with 48h delay, `3 qualified -> 1 reward`, monthly cap `2`, deferred rollover.
  - referral UX wired in bot:
    - home CTA `referral:open`;
    - `/referral` and `/invite` commands;
    - reward choice callbacks `referral:reward:MEGA_PACK_15|PREMIUM_STARTER`.
  - referral rewards now use explicit user choice flow:
    - worker marks eligible slots as `awaiting_choice` (no auto-grant);
    - `claim_next_reward_choice` applies selected reward.
  - hardening coverage added:
    - duplicate claim idempotency (sequential + concurrent callback replay);
    - worker-vs-choice race safety test.
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
  - provider-specific on-call alert routing:
    - event templates for Slack/PagerDuty/generic webhook;
    - escalation policy tiers (`ops_l1/ops_l2/ops_l3`) with per-event overrides via env JSON.
  - bot promo purchase wiring:
    - promo discount success now returns targeted `buy:<product_code>:promo:<redemption_id>` callbacks;
    - payment handler accepts promo-bound buy callbacks and settles discount through purchase flow.
  - Telegram webhook smoke scenarios:
    - `/promo` redeem -> buy callback -> precheckout -> successful payment -> credit;
    - referral reward choice callback duplicate replay safety;
    - dispatcher router-attachment issue fixed via singleton dispatcher reuse.
- Technical spec source of truth: `TECHNICAL_SPEC_ENERGY_STARS_BOT.md`.

## Critical Notes
- `.env` is local-only and must never be committed.
- Bot token is already configured locally; rotate token before production webhook go-live.
- Docker services are available in this runtime (`postgres`, `redis`) and currently running.
- Latest full validation run in this branch: `139 passed`.
- Current Alembic head: `f6a7b8c9d0e1`.

## Immediate Next Steps (Priority)
1. M10/M11 remaining hardening:
  - dedicated external Telegram sandbox runbook for real Stars provider validation;
  - promo incident response runbook (campaign unpause/manual handling).
2. Product/ops maturity:
  - dashboard for promo conversion/failure/guard triggers.

## Validation Commands
- `TMPDIR=/tmp .venv/bin/python -m pytest -q`
- `.venv/bin/ruff check app tests alembic scripts`
- `TMPDIR=/tmp .venv/bin/alembic heads`
