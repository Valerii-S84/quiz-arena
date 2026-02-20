# Next Agent Handoff (2026-02-19)

## Update (2026-02-20, M11-A analytics foundation)
- Added analytics data model and migration:
  - `analytics_events` table for event ingestion;
  - `analytics_daily` table for daily KPI aggregates;
  - migration: `alembic/versions/f0e1d2c3b4a5_m15_add_analytics_tables.py`.
- Added aggregation service + scheduled worker:
  - `app/services/analytics_daily.py` builds Berlin-day snapshots;
  - `app/workers/tasks/analytics_daily.py` runs hourly (`q_low`) and upserts daily rows.
- Added internal analytics KPI endpoint:
  - `GET /internal/analytics/executive` (token + IP allowlist protected).
- Wired referral reward emitted events into analytics ingestion:
  - `app/workers/tasks/referrals.py` now writes both to `outbox_events` and `analytics_events`.
- Added tests:
  - `tests/api/test_internal_analytics_auth.py`,
  - `tests/integration/test_internal_analytics_dashboard_integration.py`,
  - `tests/integration/test_analytics_daily_aggregation_integration.py`,
  - `tests/workers/test_analytics_daily_task.py`.

## Update (2026-02-20, standalone ops UI + referral notifications feed)
- Delivered standalone ops web UI (internal IP allowlist protected):
  - `GET /ops/promo`,
  - `GET /ops/referrals`,
  - `GET /ops/notifications`.
- Added internal referral notifications feed API:
  - `GET /internal/referrals/events` (filters: `window_hours`, `event_type`, `limit`).
- Wired referral reward emitted events into persistence for feed visibility:
  - worker now records `referral_reward_milestone_available` and `referral_reward_granted`
    into `outbox_events` with delivery status `SENT`/`FAILED`.
- Added tests:
  - `tests/api/test_ops_ui.py`,
  - `tests/integration/test_internal_referrals_events_integration.py`,
  - updated `tests/workers/test_referrals_task.py` and `tests/api/test_internal_referrals_auth.py`.

## Update (2026-02-20, referral reward notifications channel)
- Added external notification events for referral reward lifecycle:
  - `referral_reward_milestone_available`,
  - `referral_reward_granted`.
- Wired notification dispatch into referral reward-distribution worker:
  - `run_referral_reward_distribution_async` now emits alerts via `send_ops_alert` when milestone/reward counts are present.
- Added alert routing defaults in provider-aware alerts service:
  - both events route as `info` / `ops_l3` to `slack + generic` by default.
- Added tests:
  - `tests/workers/test_referrals_task.py` (worker notification dispatch helper),
  - `tests/services/test_alerts.py` (event routing for referral milestone notification).

## Update (2026-02-20, referral manual review workflow)
- Delivered referral triage internal APIs:
  - `GET /internal/referrals/review-queue` (window/status-filtered queue);
  - `POST /internal/referrals/{referral_id}/review` (manual decisions).
- Implemented safe decision transitions:
  - `CONFIRM_FRAUD` -> `REJECTED_FRAUD` (with enforced minimum fraud score);
  - `REOPEN` -> `STARTED` (for `REJECTED_FRAUD`/`CANCELED`);
  - `CANCEL` -> `CANCELED` (for `STARTED`/`REJECTED_FRAUD`);
  - invalid transitions return `E_REFERRAL_REVIEW_DECISION_CONFLICT`.
- Added tests:
  - `tests/api/test_internal_referrals_auth.py` (auth coverage for new endpoints),
  - `tests/integration/test_internal_referrals_review_integration.py` (queue + decision flow).
- Added ops runbook:
  - `docs/runbooks/referrals_fraud_review.md`.

## Update (2026-02-20, promo admin workflow + refund rollback automation)
- Delivered internal promo admin operations endpoints:
  - `GET /internal/promo/campaigns` (filters: `status`, `campaign_name`, `limit`);
  - `POST /internal/promo/campaigns/{promo_code_id}/status` (safe mutable transitions);
  - `POST /internal/promo/refund-rollback` (manual refund rollback, idempotent response behavior).
- Added campaign safety rules for manual unpause flow:
  - mutable transitions restricted to `ACTIVE <-> PAUSED`;
  - attempts to reactivate `DEPLETED/EXPIRED` via this endpoint return `E_PROMO_STATUS_CONFLICT`.
- Added refund-driven promo rollback automation (`PR_REVOKED` flow):
  - new periodic worker task `run_refund_promo_rollback` every 5 minutes;
  - scans refunded promo purchases and idempotently sets linked `promo_redemptions.status='REVOKED'`.
- Accounting decision implemented per spec:
  - refund rollback does not decrement `promo_codes.used_total`.
- Added tests:
  - `tests/integration/test_internal_promo_admin_integration.py`,
  - `tests/integration/test_payments_idempotency_integration.py::test_refund_promo_rollback_job_revokes_discount_redemption_without_decrementing_usage`,
  - `tests/workers/test_payments_reliability_task.py` (new wrapper coverage for rollback task).

## Update (2026-02-20, referrals dashboard + fraud triage)
- Delivered referral fraud-triage dashboard endpoint:
  - `GET /internal/referrals/dashboard`
  - internal auth parity (`X-Internal-Token` + IP allowlist).
- Dashboard output includes:
  - referral funnel/status metrics in selected time window;
  - fraud rates and rejected-fraud totals;
  - top suspicious referrers and recent fraud cases for manual triage.
- Added periodic referral fraud observability monitor:
  - `run_referrals_fraud_alerts` every 15 minutes;
  - threshold-based alert event `referral_fraud_spike_detected`.
- Added env-driven thresholds:
  - `REFERRALS_ALERT_WINDOW_HOURS`,
  - `REFERRALS_ALERT_MIN_STARTED`,
  - `REFERRALS_ALERT_MAX_FRAUD_REJECTED_RATE`,
  - `REFERRALS_ALERT_MAX_REJECTED_FRAUD_TOTAL`,
  - `REFERRALS_ALERT_MAX_REFERRER_REJECTED_FRAUD`.
- Added tests:
  - `tests/api/test_internal_referrals_auth.py`,
  - `tests/integration/test_internal_referrals_dashboard_integration.py`,
  - `tests/services/test_referrals_observability.py`,
  - `tests/workers/test_referrals_observability_task.py`.

## Update (2026-02-20, offers dashboard + thresholds)
- Delivered dedicated offers funnel dashboard endpoint:
  - `GET /internal/offers/dashboard`
  - internal auth parity (`X-Internal-Token` + IP allowlist).
- Added offers CTA attribution in purchase flow:
  - offer keyboard callbacks now include `offer` payload (`buy:<product>:offer:<impression_id>`);
  - payment handler writes `clicked_at` and `converted_purchase_id` into `offers_impressions`.
- Added periodic offers monitoring job:
  - `run_offers_funnel_alerts` every 15 minutes;
  - threshold-based ops alerts:
    - `offers_conversion_drop_detected`,
    - `offers_spam_anomaly_detected`.
- Added env-driven thresholds:
  - `OFFERS_ALERT_WINDOW_HOURS`,
  - `OFFERS_ALERT_MIN_IMPRESSIONS`,
  - `OFFERS_ALERT_MIN_CONVERSION_RATE`,
  - `OFFERS_ALERT_MAX_DISMISS_RATE`,
  - `OFFERS_ALERT_MAX_IMPRESSIONS_PER_USER`.
- Added tests:
  - `tests/api/test_internal_offers_auth.py`,
  - `tests/integration/test_internal_offers_dashboard_integration.py`,
  - `tests/bot/test_payments_handler.py`,
  - `tests/services/test_offers_observability.py`,
  - `tests/workers/test_offers_observability_task.py`.

## Update (2026-02-19, promo dashboard)
- Delivered dedicated promo observability endpoint:
  - `GET /internal/promo/dashboard`
  - internal auth parity with redeem endpoint (`X-Internal-Token` + IP allowlist).
- Dashboard output now includes:
  - promo conversion metrics (`attempts accepted/failed`, `discount reservation->applied`);
  - failure-rate breakdown by attempt result (`INVALID`, `EXPIRED`, `NOT_APPLICABLE`, `RATE_LIMITED`);
  - guard trigger indicators (`candidate abusive hashes`, `paused campaign totals/recent`).
- Added/updated tests:
  - `tests/api/test_internal_promo_auth.py` (dashboard auth coverage),
  - `tests/integration/test_internal_promo_dashboard_integration.py` (metrics correctness).
- Milestone ops note updated:
  - `docs/milestones/M10_ops.md` now records the dashboard endpoint as implemented.

## What was completed
- Friend challenge flow implemented and stabilized:
  - 12-round plan with fixed level sequence `A1x3 + A2x6 + B1x3`.
  - Both players receive the same question per round.
  - Opponent labels resolve to username/first name instead of generic `Freund`.
  - Creator can continue all rounds without waiting; round/final score updates are synced.
  - Free quota and paid ticket/premium rules wired for friend challenges.
- Friend challenge invite UX updated:
  - Share-first flow with Telegram native share URL (`Link teilen`).
  - Separate action to start duel after link sharing.
- Promo handling fixed:
  - Promo is no longer auto-captured from unrelated text by default.
  - Promo redemption runs only from explicit promo entry points.
  - Internal promo integration tests pass.
- `ARTIKEL_SPRINT` adaptive progression fixed:
  - New users start at `A1`.
  - Progress now persists across sessions/days in new table `mode_progress`.
  - Existing users without a progress row are backfilled from most recent `ARTIKEL_SPRINT` history.
  - Bounds clamped to mode range (`A1..B2`) to avoid invalid upward jumps.

## New DB migration
- Added migration:
  - `alembic/versions/d5e6f7a8b9c0_m14_add_mode_progress_table.py`
- Added migration:
  - `alembic/versions/f0e1d2c3b4a5_m15_add_analytics_tables.py`
- Current DB head verified: `f0e1d2c3b4a5`.
- Promo dashboard delivery in this update did not require DB migrations.

## Important operational notes
- Integration tests truncate core tables including:
  - `quiz_questions`
  - `promo_codes` and related promo tables
- If tests are run on shared/dev DB, re-seed after tests:
  - Re-import quiz bank.
  - Recreate required promo codes (e.g. `CHIK`) if needed.

## Validation performed
- `pytest -q -s tests/game/test_adaptive_difficulty.py tests/integration/test_artikel_sprint_progress_integration.py tests/test_data_model_metadata.py` -> passed.
- `pytest -q -s tests/integration/test_friend_challenge_integration.py::test_friend_challenge_default_uses_12_round_plan_with_level_mix_and_free_energy` -> passed.
- `ruff` checks for touched files -> passed.
- `pytest -q -s tests/api/test_internal_promo_auth.py tests/integration/test_internal_promo_dashboard_integration.py` -> passed.
- `ruff check app/api/routes/internal_promo.py app/db/repo/promo_repo.py tests/api/test_internal_promo_auth.py tests/integration/test_internal_promo_dashboard_integration.py` -> passed.

## Runtime state at handoff
- Background API and worker processes were explicitly stopped before handoff.
- Workspace prepared for clean startup by next agent.
