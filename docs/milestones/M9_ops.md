# M9 Ops

## Added
- New referral maintenance workers:
  - `run_referral_qualification_checks` (every 10 minutes, `q_normal`);
  - `run_referral_reward_distribution` (every 15 minutes, `q_normal`);
  - monthly deferred re-check at `00:05` Berlin on day 1.
- New Celery task module:
  - `app/workers/tasks/referrals.py`.
- Updated task registration:
  - `app/workers/celery_app.py`
  - `app/workers/tasks/__init__.py`

## Operational Notes
- Referral rewards are currently auto-granted using default reward path (Mega Pack equivalent), without interactive user selection.
- Reward issuance is idempotency-protected via deterministic keys on ledger/mode access writes.

## Missing for Next Milestones
- Operator dashboard for referral funnel and fraud triage.
- Alerting hooks for abnormal referral velocity/fraud spikes.
- User-facing reward-choice handler and communication templates.
