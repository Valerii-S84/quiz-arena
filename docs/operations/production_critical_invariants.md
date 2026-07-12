# Production critical invariants

This page describes code-level checks added before controlled deploy. The checker is read-only.

Primary command:

```bash
.venv/bin/python scripts/production_critical_invariants.py --json
```

Human output:

```bash
.venv/bin/python scripts/production_critical_invariants.py
```

Exit code:
- `0`: no active `P0`/`P1` invariant failures;
- non-zero: at least one active `P0`/`P1` failure.

`P2` results are review items unless they directly imply unsafe deploy behavior, privacy leakage, wrong entitlement/payment state, silent messaging loss, or data corruption.

## Covered checks

- `paid_without_entitlement`
- `paid_uncredited_age_minutes`
- `paid_without_charge_id`
- `reconciliation_diff_nonzero`
- `expired_active_entitlements_count`
- `webhook_processing_failed_or_stuck`
- `daily_cup_expected_delivery_zero_outcomes`
- `tournament_round_expected_delivery_zero_outcomes`
- `private_tournament_round_delivery_gap`
- `telegram_delivery_failure_rate`
- `telegram_blocked_users_count`
- `worker_task_heartbeat_stale`
- `queue_oldest_message_age_seconds`
- `streak_update_stale`
- `global_best_streak_source_inconsistent`
- `analytics_daily_stale`
- `telegram_delivery_pending_stale`

## Safety

The checker must not:
- write production data;
- run migrations;
- restart services;
- replay tasks;
- send Telegram messages;
- print secrets or raw Telegram chat ids.

The scheduled alert task writes only `production_invariant_alerts` rows. It does not repair, reconcile, resend, or recover data.

## Before Controlled Deploy

Do not use this checker as production proof until the production migration and code deploy are complete. Before deploy it only proves repository readiness.

After controlled deploy and migration:
1. Run the checker in read-only mode.
2. Verify no `P0`/`P1` failures.
3. Inspect any `P2` failures against the runbooks.
4. Keep auto-recovery and live reconciliation disabled unless a separate approved task enables them.
