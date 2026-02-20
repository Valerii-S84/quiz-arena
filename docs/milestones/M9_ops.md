# M9 Ops

## Added
- New referral maintenance workers:
  - `run_referral_qualification_checks` (every 10 minutes, `q_normal`);
  - `run_referral_reward_distribution` (every 15 minutes, `q_normal`);
  - monthly deferred re-check at `00:05` Berlin on day 1.
- New referral observability worker:
  - `run_referrals_fraud_alerts` (every 15 minutes, `q_normal`).
- New Celery task module:
  - `app/workers/tasks/referrals.py`.
- New internal referral dashboard endpoint:
  - `GET /internal/referrals/dashboard` (internal token + IP allowlist).
- New internal referral triage endpoints:
  - `GET /internal/referrals/review-queue`;
  - `POST /internal/referrals/{referral_id}/review`.
- New runbook:
  - `docs/runbooks/referrals_fraud_review.md`.
- Updated task registration:
  - `app/workers/celery_app.py`
  - `app/workers/tasks/__init__.py`
- New referral fraud alert event:
  - `referral_fraud_spike_detected` (`slack + generic`, `warning`, `ops_l2`).
- New referral reward notification events:
  - `referral_reward_milestone_available` (`slack + generic`, `info`, `ops_l3`);
  - `referral_reward_granted` (`slack + generic`, `info`, `ops_l3`).

## Operational Notes
- Referral reward distribution can run in `awaiting_choice` mode (no auto-grant) and is finalized by explicit user reward-choice callback.
- Reward issuance is idempotency-protected via deterministic keys on ledger/mode access writes.
- Fraud-spike thresholds are configurable through env:
  - `REFERRALS_ALERT_WINDOW_HOURS`,
  - `REFERRALS_ALERT_MIN_STARTED`,
  - `REFERRALS_ALERT_MAX_FRAUD_REJECTED_RATE`,
  - `REFERRALS_ALERT_MAX_REJECTED_FRAUD_TOTAL`,
  - `REFERRALS_ALERT_MAX_REFERRER_REJECTED_FRAUD`.

## Missing for Next Milestones
- Analytics foundation over emitted referral events (`events` + daily aggregates + KPI surfaces).
