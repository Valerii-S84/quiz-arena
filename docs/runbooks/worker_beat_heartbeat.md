# Worker and beat heartbeat runbook

## Symptom

Checker reports `worker_task_heartbeat_stale`, or scheduled user-visible tasks stop executing.

## Checker

```bash
.venv/bin/python scripts/production_critical_invariants.py --json
```

## Severity

`P1` for critical payment, Telegram update, Daily Cup, private tournament, and invariant alert tasks. `P2` for less direct freshness tasks such as analytics and premium expiry.

## What To Check

- `worker_task_heartbeats.task_name`
- `schedule_key`
- `last_started_at`
- `last_success_at`
- `last_failed_at`
- `last_error_hash`
- `consecutive_failures`
- Celery worker/beat container status.

## Do Not Do Without Approval

- Do not restart production services.
- Do not replay stale tasks.
- Do not run migrations.
- Do not enable auto-recovery or live reconciliation.

## Dry-Run Path

Read heartbeat rows and compare against `app.workers.task_heartbeat.get_critical_task_heartbeats()`. If a task is stale, identify whether the issue is beat scheduling, worker execution, DB connectivity, or task failure.

## Escalation

Escalate immediately for stale payment reliability, Telegram update reliability, Daily Cup lifecycle, private tournament lifecycle, or production invariant alert tasks.

## Rollback / Disable

If heartbeat writes fail but task work succeeds, user flow should continue. If the wrapper itself is suspected, revert the deploy in a separate approved rollback task.
