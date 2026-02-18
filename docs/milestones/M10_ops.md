# M10 Ops

## Added
- New internal endpoint: `POST /internal/promo/redeem`.
- New Celery periodic jobs:
  - `run_promo_reservation_expiry` every 1 minute;
  - `run_promo_campaign_status_rollover` every 10 minutes;
  - `run_promo_bruteforce_guard` every 1 minute.
- Structured logs for promo maintenance and autopause outcomes.
- Generic ops alert webhook hook (`OPS_ALERT_WEBHOOK_URL`) for:
  - promo campaign autopause events;
  - payment reconciliation diffs;
  - payment recovery review-required outcomes.

## Missing for Next Milestones
- Provider-specific on-call integration policy (routing keys, escalation tiers, alert dedup strategy).
- Operational runbook for campaign unpause / manual promo incident handling.
- Dedicated dashboard for promo conversion, failure rates, and guard triggers.
