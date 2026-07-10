# Telegram delivery failures runbook

## Symptom

Users report missing Daily Cup, tournament, beaten, or offer messages. Checker reports:
- `telegram_delivery_failure_rate`;
- `telegram_blocked_users_count`;
- `daily_cup_expected_delivery_zero_outcomes`;
- `tournament_round_expected_delivery_zero_outcomes`;
- `private_tournament_round_delivery_gap`.

## Checker

```bash
.venv/bin/python scripts/production_critical_invariants.py --json
```

## Severity

- `P1`: zero delivery outcomes for expected mass messaging or failure-rate spike.
- `P2`: blocked candidates review unless it affects a mass send.

## What To Check

- `telegram_delivery_attempts.flow`
- `correlation_id`
- `status`
- `failure_code`
- `telegram_error_code`
- `is_blocked_candidate`
- aggregate counts only; avoid exposing raw user data.

## Do Not Do Without Approval

- Do not send manual Telegram messages.
- Do not replay Celery tasks.
- Do not delete users.
- Do not permanently suppress blocked candidates.
- Do not edit production data by hand.

## Dry-Run Repair

Use the repair planner service from an approved diagnostic shell only after migration/deploy:

```python
from app.services.messaging_repair_planner import plan_tournament_messaging_repair
```

Allowed dry-run flows:
- `daily_cup_round_messaging`
- `private_tournament_round_messaging`

The planner returns expected targets, existing attempts, missing targets, failed targets, skipped targets, and safe replay candidates. It does not send messages.

## Escalation

Escalate to owner approval when:
- any `P1` delivery gap is active;
- failure rate spike includes Telegram 403/429 mix;
- a replay would affect more than one user;
- there is uncertainty about user consent or duplicate messaging.

## Rollback / Disable

If alert noise is caused by bad checker logic, disable the scheduled alert task in code/config in a separate approved PR or revert the deploy. Do not disable delivery tracking tables.
