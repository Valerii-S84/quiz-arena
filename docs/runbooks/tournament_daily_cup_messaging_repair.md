# Tournament and Daily Cup messaging repair runbook

## Symptom

Checker reports:
- `daily_cup_expected_delivery_zero_outcomes`;
- `tournament_round_expected_delivery_zero_outcomes`;
- `private_tournament_round_delivery_gap`.

## Checker

```bash
.venv/bin/python scripts/production_critical_invariants.py --json
```

## Severity

`P1` when expected tournament or Daily Cup messaging has zero terminal outcomes or missing participant outcomes.

## What To Check

- tournament id;
- tournament type and status;
- participant count;
- delivery attempts for the matching `flow` and `correlation_id`;
- `SENT`, `FAILED`, `SKIPPED` counts.

## Do Not Do Without Approval

- Do not manually message users.
- Do not replay round messaging tasks.
- Do not mutate tournament status.
- Do not delete or overwrite delivery attempt rows.

## Dry-Run Repair

Use `app.services.messaging_repair_planner.plan_tournament_messaging_repair` with:
- `flow="daily_cup_round_messaging"` for Daily Cup round/final messaging;
- `flow="private_tournament_round_messaging"` for private tournament round messaging.

The planner is dry-run only. It preserves the full phase-specific target id, so
an older `round:1` `SENT` outcome does not suppress a missing current `round:2`,
`status:completed`, or cancel-phase target. Safe replay candidates are limited
to missing expected targets or retryable failures that remain below the delivery
attempt limit. Permanent Telegram failures such as forbidden, blocked user, chat
not found, and permanent bad request are not safe replay candidates.

## Escalation

Escalate before any replay. Approval must specify:
- flow;
- tournament id;
- target set;
- allowed replay method;
- rollback/stop condition.

## Rollback / Disable

If the alert is false positive, fix checker logic in a PR. Do not patch production data to hide the alert.
