# Production critical flows hardening tracker 2026-07-10

Status: `CODE_READY_FOR_CONTROLLED_DEPLOY` at code level after local gates, pending controlled deploy, production migration, and post-deploy smoke in separate tasks.

Safety boundary for this PR:
- no deploy;
- no production DB writes;
- no production migrations;
- no production restarts;
- no task replay;
- no manual messaging;
- no `.env*`, secrets, deploy config, or `docker-compose.prod.yml` changes;
- auto-recovery remains off;
- live reconciliation is not enabled.

## Gap matrix closure

| Blocker | Code area | Invariant added | Migration | Tests |
| --- | --- | --- | --- | --- |
| Durable Telegram delivery outcomes | `telegram_delivery_attempts`, `app/services/telegram_delivery.py`, Daily Cup/private tournament/beaten flows | every expected target is `SENT`, `FAILED`, or `SKIPPED`; duplicate runs use DB-backed idempotency | `b6c7d8e9f012_m56_production_reliability_foundation.py` | delivery repo/service/worker tests |
| Daily Cup push fake sent idempotency | `daily_cup_registration_push.py` | analytics sent event is written only after Telegram send and delivery `SENT` | yes | registration push unit tests |
| Worker/beat heartbeat | `worker_task_heartbeats`, `app/workers/task_heartbeat.py` | task start/success/failure and last-success are durable; stale checker has registry | yes | heartbeat and wrapper tests |
| Production invariant checker | `app/services/production_invariants.py`, `scripts/production_critical_invariants.py` | read-only P0/P1/P2 checks with stable JSON/text output | no | checker script/service tests |
| Durable P1/P2 alerts | `production_invariant_alerts`, `production_invariant_alerts.py` | active failures upsert/reopen OPEN alerts; OK checks resolve existing OPEN alert | yes | alert task and repo lifecycle tests |
| Premium expiry lifecycle | `premium_expiry.py`, `EntitlementsRepo` | expired ACTIVE premium can be marked `EXPIRED` idempotently; effective lookup remains time-aware | no extra table | premium expiry tests |
| Telegram blocked/failure state | delivery attempt failure classification | 403/bot blocked/chat missing becomes failed blocked candidate; future mass send can skip known blocked candidate | yes | Telegram delivery service tests |
| Messaging repair-ready path | `messaging_repair_planner.py` | dry-run plan lists expected, existing, missing, failed, skipped, safe replay candidates without sending | no | repair planner tests |
| Streak/global/analytics freshness | production invariant checker | stale streak, inconsistent global source, stale analytics, and stuck scheduled offer delivery attempts are visible | no | checker coverage tests |

## Acceptance criteria

Code-level criteria met:
- durable delivery attempt model/repo/service added;
- Daily Cup registration, reminders, round/cancel, private tournament, and beaten notification entrypoints record outcomes;
- heartbeat wrapper and critical task registry added;
- read-only invariant checker added;
- durable alert task added;
- premium expiry task added but not run in production;
- dry-run repair planner added;
- runbooks and operations docs added.

Deploy-only criteria not performed in this PR:
- apply migration on production;
- deploy worker/API/beat code;
- run production checker after migration;
- execute post-deploy smoke;
- confirm monitoring and ads readiness.

## Local evidence

Targeted checks completed during implementation:
- delivery focused suite: `31 passed`;
- heartbeat/premium focused suites: `19 passed`, `25 passed`;
- invariant/repair/alert suites: `23 passed`;
- formatting/lint focused checks passed for changed code.

Full gate results are recorded in the final PR report.
