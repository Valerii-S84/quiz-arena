# M10 Ops

## Added
- New internal endpoint: `POST /internal/promo/redeem`.
- New Celery periodic jobs:
  - `run_promo_reservation_expiry` every 1 minute;
  - `run_promo_campaign_status_rollover` every 10 minutes;
  - `run_promo_bruteforce_guard` every 1 minute.
- Structured logs for promo maintenance and autopause outcomes.
- Provider-specific ops alert routing with escalation policy:
  - channels: `generic`, `slack`, `pagerduty`;
  - default event routing:
    - `promo_campaign_auto_paused` -> `warning`, `ops_l2`, `slack + generic`;
    - `payments_reconciliation_diff_detected` -> `critical`, `ops_l1`, `pagerduty + slack + generic`;
    - `payments_recovery_review_required` -> `error`, `ops_l1`, `pagerduty + slack + generic`;
  - optional per-event overrides through `OPS_ALERT_ESCALATION_POLICY_JSON`.
- Generic webhook channel (`OPS_ALERT_WEBHOOK_URL`) remains supported for backward compatibility.
- New provider env settings:
  - `OPS_ALERT_SLACK_WEBHOOK_URL`;
  - `OPS_ALERT_PAGERDUTY_EVENTS_URL` (default `https://events.pagerduty.com/v2/enqueue`);
  - `OPS_ALERT_PAGERDUTY_ROUTING_KEY`;
  - `OPS_ALERT_ESCALATION_POLICY_JSON`.
- Alert events wired in workers:
  - promo campaign autopause events;
  - payment reconciliation diffs;
  - payment recovery review-required outcomes.
- New runbook:
  - `docs/runbooks/telegram_sandbox_stars_smoke.md` for external Telegram sandbox validation of promo/payment and referral duplicate-callback safety.
  - `docs/runbooks/promo_incident_response.md` for promo autopause triage and safe manual unpause procedure.

## Missing for Next Milestones
- Dedicated dashboard for promo conversion, failure rates, and guard triggers.
