# Production critical flows audit plan 2026-07-10

Статус аудиту: Done.

Readiness: `NOT_READY_P0_P1_BLOCKERS`.

Scope: read-only audit of repository, production runtime, DB, worker/beat tasks, logs and test coverage for critical Quiz Arena flows before scaling and advertising.

Safety:
- no deploy;
- no production DB writes;
- no `.env*`;
- no secrets;
- no migrations;
- no restarts;
- no task replay;
- no manual messaging;
- no manual repair.

Supporting evidence file: `reports/production_runtime_findings_20260710.md`.

## Executive summary

Production is alive, API health is OK, PostgreSQL/Redis are ready, worker and beat are running, queues are empty, Telegram webhook has no pending updates, and no stale `PAID_UNCREDITED` purchase was found.

The system is still not ready for ads/scaling because critical production invariants are missing or not live:

- production code is behind `origin/main` by PR #243/#244/#245; the live server is on `1fb8a09`, while `origin/main` is `bafcf27 Complete payment reliability plan (#245)`;
- live DB does not have the PR #245 payment evidence/review tables: `telegram_update_inbox`, `payment_events`, `payment_reconciliation_reviews`;
- Daily Cup/tournament delivery has no durable sent/failed/skipped table and no alert when expected messages are not actually delivered;
- Daily Cup registration push marks analytics as sent before the Telegram send, so a transient delivery failure can be hidden by idempotency;
- worker/beat are running, but there is no durable heartbeat/invariant proving each critical periodic task executed within N minutes/hours;
- premium expiry has stale `ACTIVE` rows and no clear runtime expiry transition;
- Telegram blocked/delivery failure handling is mostly log/count based, not persistent repair-ready state.

No active P0 was confirmed during this audit. There are multiple P1 blockers.

## Final readiness status

`NOT_READY_P0_P1_BLOCKERS`.

Meaning:
- do not launch paid ads or scale user acquisition yet;
- production is usable for current low-volume traffic with limits;
- before ads, close at least the P1 set: production drift, durable messaging outcomes, heartbeat/alerts, premium expiry cleanup/review, and payment evidence schema/live invariant alignment.

## Current git/server state

| Area | Evidence | Status |
| --- | --- | --- |
| Local branch | `git rev-parse --abbrev-ref HEAD` | `main` |
| Local/origin HEAD | `bafcf2730211355e66718d3dbb43b94e69424bca` | includes PR #245 |
| Latest local commit | `bafcf27 Complete payment reliability plan (#245)` | expected post-merge state |
| Local status before audit reports | `git status --short` | only `?? reports/payment_reliability_plan_20260707.md` |
| PR #245 | GitHub connector | merged at `2026-07-10T12:00:32Z`, CI success on run `29087110146` |
| Production path | `/opt/quiz-arena` | checked read-only |
| Production branch | `main` | checked read-only |
| Production HEAD | `1fb8a096b625ac6955c5a332467ba4291a3d467e` | behind local/origin |
| Production untracked files | server `git status --short` | `backup_pre_website_analytics_20260604_184020.sql`, `manual_compensation_exports/` |
| Public health | `GET /health` | OK |
| Public ready | `GET /api/ready` | `404`, expected edge behavior |
| Internal ready | container-local `/ready` | DB and Redis OK |
| Core containers | `docker compose ps`, `docker inspect` | API/worker/beat/PostgreSQL/Redis/frontend running since `2026-06-29`, restart count `0` |
| Queues | Redis `LLEN q_high/q_normal/q_low` | all `0` |

Primary production gap: live server does not correspond to current `origin/main`. This blocks any claim that PR #244/#245 payment reliability fixes are protecting production.

## Agent roles used

| Role | Output |
| --- | --- |
| Agent A: Виконавець аудиту | code/test audit for webhook, payments, worker/beat, delivery, Redis/cache, analytics |
| Agent B: Контролер scope та безпеки | approved only read-only Git/runtime/log/SQL/getWebhookInfo commands; blocked state-changing commands |
| Agent C: Reviewer критичних потоків | risk review focused on production invariants and silent failure paths |
| Agent D: Incident auditor | incident reconstruction for tournament messaging and `Rekord 87` |
| Agent E: Фінальний аудитор | this synthesized report |

## Incident reconstruction

### Incident 1: tournament invites / round messaging

Verdict: `LIKELY_ROOT_CAUSE` for missing round messages; `INSUFFICIENT_EVIDENCE` for actual Telegram invite delivery outage.

Evidence:
- Code: `DAILY_CUP_MIN_PARTICIPANTS = max(4, ...)`; Daily Cup close/start cancels when participants are below the minimum.
- DB: `DAILY_ARENA` was `CANCELED` every day from `2026-06-30` through `2026-07-09`, with `0-3` participants.
- DB: no active/stuck tournament rows were found.
- DB: last completed Daily Arena with matches was `2026-06-29`, with `4` participants, `6` matches, `12` round scores.
- Analytics: `daily_cup_invite_registration_push_sent`, `daily_cup_last_call_reminder_sent`, and `daily_cup_prestart_reminder_sent` existed through `2026-07-09`.
- Code gap: Daily Cup push analytics are inserted before the Telegram send, so those events do not prove delivery.
- Logs: worker/beat logs over 7 days had `0` lines, so they cannot prove per-task delivery behavior.
- Runtime: Celery stats show Daily Cup tasks executed since worker start, but stats do not provide last-success timestamp or per-user delivery result.

Conclusion:
- Round messages did not go after `2026-06-29` because Daily Arena did not reach participant minimum and no rounds started. This is expected lifecycle behavior, not a confirmed round-messaging bug.
- If the reported issue was “users did not receive invites in Telegram,” current evidence cannot confirm or refute it. The system records push analytics before send and has no durable sent/failed/skipped result table.
- Why messages “started again” cannot be conclusively proven from current evidence. The audit saw invite-push analytics through `2026-07-09`; on `2026-07-10` the regular invite time had not yet been fully verified in the collected DB evidence.

Minimum fix-task:
- add durable `daily_cup_message_deliveries` / generic `telegram_delivery_attempts` rows with `sent|failed|skipped`, reason, task name, target user and correlation id;
- add alert if expected Daily Cup/tournament delivery has `eligible > 0` and `sent + failed + skipped = 0` after N minutes.

### Incident 2: daily streak / record stuck at 87

Verdict: `EXPECTED_BEHAVIOR` for global record `87`; `INSUFFICIENT_EVIDENCE` for any specific user’s personal streak without user ID.

Evidence:
- Production DB: `streak_state` has `max_best_streak = 87`, `max_current_streak = 33`.
- Production DB: no users have `current_streak > 87` or `best_streak > 87`.
- Production DB: streak rows are actively updating; latest `updated_at` was `2026-07-10 12:32:31`, and `232` users had `today_status = PLAYED`.
- Production Redis: `quiz_arena:global_best_streak` key was absent in db0/db1/db2.
- Production code at live commit `1fb8a09`: home/global record reads DB max directly, not the newer current-main cache module.
- Current main code has `app/core/global_best_streak_cache.py`, but it is not deployed on production.

Conclusion:
- `Rekord 87` is the all-time global best streak in production DB. It should not change until someone reaches `best_streak > 87`.
- Daily streak updates are not globally frozen.
- If the issue is a specific user whose personal streak should change, the audit needs that user id/chat id and the exact expected activity dates.

Minimum fix-task:
- add a read-only admin check for `streak_state` freshness and `global_best_streak` source;
- add alert if no `streak_state.updated_at` moves for N hours while quiz activity exists;
- add tests around global record display and cache invalidation before deploying the current-main cache path.

## Critical flows matrix

| Flow | User-visible promise | Entrypoints and dependencies | DB/cache/tasks | Tests seen | Current invariant status | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| Telegram webhook ingestion | Telegram updates are accepted once, processed or durably failed/reviewed, duplicates do not double-process | `app/api/routes/telegram_webhook.py`, `app/workers/tasks/telegram_updates.py`, `app/workers/tasks/telegram_updates_processing.py` | `processed_updates`; current main also adds `telegram_update_inbox` for payment evidence; Celery `process_telegram_update`; Redis broker/FSM | `tests/api/test_telegram_webhook.py`, `tests/workers/test_telegram_updates_task.py`, idempotency tests | Production has update-level idempotency and 0 stuck rows; live lacks PR #245 payment inbox; no alert if webhook processing fails repeatedly except limited outbox events | P1 |
| Payment invoice/precheckout/success/refund/reconciliation | Paid users get entitlement/assets or review/alert; refunds are reconcilable | `payments_buy_completion.py`, `payments.py`, `payments_runtime.py`, purchase service, payment reliability tasks | `purchases`, `entitlements`, `ledger_entries`, current main `payment_events`, `payment_reconciliation_reviews`; Celery payment schedules | broad payment unit/integration tests in current main; PR #245 CI green | Production has no stale `PAID_UNCREDITED`, but is behind PR #245 and has one paid/credited premium row missing charge id; live review schema absent | P1 |
| Tournament invites / round messaging | Eligible users receive invite/round messages or a recorded failed/skipped reason | Daily Cup/private tournament tasks, Telegram Bot API | `tournaments`, `tournament_participants`, `tournament_matches`, analytics events; Celery daily/private tasks | task entrypoint tests, Daily Cup push unit tests | Round absence after Jun29 is expected due min participants; delivery proof missing; analytics before send can hide failures | P1 |
| Daily Cup lifecycle and messaging | Scheduled cup transitions through invite/reminder/start/round/final/cancel states | `daily_cup_schedule.py`, `daily_cup_async.py`, `daily_cup_rounds.py`, `daily_cup_messaging.py` | `tournaments`, `tournament_participants`, `tournament_round_scores`, analytics; Celery beat | Daily Cup worker tests and units | Lifecycle runs/cancels correctly in DB; no durable per-user delivery outcome; no stuck-cup alert table | P1 |
| Private tournament lifecycle and messaging | Private tournament created/started/advanced/canceled with delivery outcome | `tournaments_async.py`, `tournaments_messaging.py`, `tournaments_messaging_delivery.py` | tournament tables; Celery `run_private_tournament_rounds` | task entrypoint tests | Context can silently return no-op; enqueue failures are warnings; no durable repair-ready delivery state | P1 |
| Beaten / duel notifications | Eligible users get notification or explicit skip/failure reason | `arena_duels_notification_delivery.py`, arena duel services | analytics unique events; no delivery table | `tests/workers/test_arena_duels_notifications.py` | Failure not persisted as repair-ready row; no production threshold alert | P2 |
| Energy regeneration / premium bypass | Free energy regenerates; premium bypass does not corrupt free accounting | `energy_consume_quiz.py`, `energy_models.py`, energy repo/service | `energy_state`, ledger; premium entitlement lookup | energy and capacity tests | Code path looks locally consistent; need production negative/stuck monitor | P2 |
| Scheduled offers / upsells | Scheduled/eligible offers are sent or skipped/failed with reason | offers evaluation/actions/observability tasks | `offers_impressions`, `analytics_events`; Celery offers alert task | offer conversion/observability tests | Better than messaging flows, but alert delivery failure is not escalated and production dashboard freshness is not invariant-tested | P2 |
| Worker/beat periodic tasks | Periodic critical tasks execute within expected intervals | `app/workers/celery_app.py`, schedule modules | Redis broker/queues; Celery stats only | schedule unit tests | Worker/beat running and counters nonzero; no durable heartbeat/last_success/alert per task | P1 |
| Telegram delivery failures and blocked users | Mass sends record sent/failed/skipped; blocked users are marked and excluded/handled | delivery modules for Daily Cup, tournaments, challenges, duels | mostly analytics/logs; no blocked-user state found | some failure tests for individual delivery functions | No central delivery attempts table; 403 does not appear to mark users blocked; no aggregate threshold alert | P1 |
| Daily streak / record / leaderboard | Daily activity updates streak; global record displays true DB/cache value | `streak/service.py`, `users_repo.py`, start/home views | `streak_state`; current main cache key `quiz_arena:global_best_streak` | streak/cache tests | Production record 87 is expected; need stale update/cache monitor before deploying current-main cache path | P2 |
| Premium expiry / entitlement lifecycle | Expired premium stops being effective and does not block new premium grants | `entitlements_repo.py`, `entitlements.py`, purchase entitlement service | `entitlements`, unique active premium index | premium purchase tests | Effective lookup is time-aware, but expired `ACTIVE` rows exist and no runtime expiry transition/job was found | P1 |
| Admin/manual repair paths | Operator can diagnose/repair narrowly with audit trail | admin bonus routes, payment checker scripts, manual compensation history | `admin_audit_log`, ledgers, reports | scattered tests | Paths exist but are not unified into read-only check + repair runbook for messaging/streak/payment anomalies | P2 |
| Redis/cache-dependent flows | Redis outages degrade visibly; cache does not hide stale critical data | Celery broker, FSM storage, health, rate limits, global streak cache current main | Redis db0/db1/db2; cache keys | health/cache/rate-limit tests | Redis healthy; global streak cache not live; no broad cache-staleness monitor | P2 |
| Analytics for monetization decisions | Purchase/paywall/offer/duel events are usable and fresh | analytics emitters, daily aggregation, internal dashboards | `analytics_events`, `analytics_daily`, `offers_impressions`, `purchases` | analytics aggregation and offer tests | Events exist, but dashboard/aggregation freshness and failed alert delivery are not production invariants | P2 |

## Production invariants matrix

| Invariant | Current evidence | Gap | Required monitor/check |
| --- | --- | --- | --- |
| Webhook update is processed, duplicate, or durable failed | `processed_updates` has processed/failed states; stuck rows `0` | live payment evidence inbox missing; no alert for repeated failures by update type | `webhook_update_processing_failures`, threshold `>0 final failures/5m` or spike |
| Paid purchase gets entitlement/assets or review | `paid_uncredited_10m=0`; no effective active premium loss found | production lacks PR #245 review schema; one credited premium missing charge id | `paid_without_entitlement`, `paid_without_charge_id`, `paid_uncredited_age_minutes` |
| Refund is reconcilable | current main has refund/reconciliation tests | production lacks new evidence tables | `reconciliation_diff_nonzero`, `refund_without_purchase_match` |
| Tournament active + eligible users produces sent/failed/skipped | no active stuck tournaments | no durable delivery outcome table | `tournament_invites_expected_vs_sent`, `round_messages_expected_vs_sent` |
| Daily Cup scheduled transitions through expected states | DB shows scheduled cups cancel/start as rules dictate | no stuck-state alert; delivery proof missing | `daily_cup_state_age`, `daily_cup_expected_vs_sent` |
| Private tournament messaging cannot silently drop | code logs warnings/counts | no durable failure row | `private_tournament_delivery_zero_result` |
| Beaten notification eligible becomes sent/skipped/failed | tests return result object | no production persistence/alert | `beaten_notification_delivery_failure_rate` |
| Energy never negative/stuck | code has range checks | no production monitor shown | `energy_negative_count`, `energy_stuck_count` |
| Offer scheduled has sent/skipped/failed and alert | offers observability exists | alert delivery result not escalated | `scheduled_offer_zero_delivery` |
| Worker/beat task runs every N interval | Celery stats counters nonzero | no durable heartbeat/last_success | `celery_task_heartbeat_age_seconds`, `beat_heartbeat_age_seconds` |
| Queue backlog does not age | Redis queue length `0` | no age metric | `queue_oldest_message_age_seconds` |
| Telegram delivery failures are aggregated | some functions count/log failures | no central persistent table | `telegram_delivery_failure_rate`, `telegram_blocked_users_count` |
| Streak/global record stays fresh | production DB max 87; rows updated today | no stale aggregation/cache monitor | `streak_update_stale`, `global_best_streak_cache_stale` |
| Premium expiry state is consistent | effective lookup ignores expired rows | expired `ACTIVE` row exists | `expired_active_entitlements_count` |
| Auto-recovery disabled unless explicitly enabled | current repo defaults safe/off; production behind | live config not read from `.env*` by design | config-safe read-only endpoint or admin status check without secrets |

## Missing tests list

First tests to add:

1. Daily Cup registration push transient Telegram failure: assert failed delivery does not create a permanent “sent” idempotency record, or creates a durable failed/skipped row eligible for retry/repair.
2. Daily Cup expected messaging invariant: eligible targets > 0 and zero delivery outcomes triggers alert/review.
3. Tournament round messaging enqueue failure: round starts but enqueue fails creates durable failed/review state.
4. Private tournament delivery partial failure: one user blocked, one sent, one skipped should persist all outcomes.
5. Worker/beat heartbeat: every critical schedule task updates heartbeat; stale heartbeat raises alert.
6. Queue backlog age: old message in `q_high/q_normal/q_low` raises alert.
7. Payment production invariant on current schema: paid without entitlement, paid without charge id, paid-uncredited age, reconciliation diff.
8. Payment PR #245 migration/runtime test against production-like schema: payment evidence stored before ACK and review rows created on validation failure.
9. Premium expiry lifecycle: expired `ACTIVE` rows cannot block a new premium purchase and are marked/handled by a controlled transition.
10. Telegram 403/blocked user behavior: blocked user is marked or has durable skipped reason and future mass sends exclude or classify it.
11. Beaten notification delivery failure: failed eligible notification is persisted as failed/skipped and visible to monitor.
12. Streak update/display: daily play updates `streak_state`; global record reads expected source; cache invalidation works in current-main cache path.
13. Offers zero delivery: scheduled offer with eligible targets but zero sent emits alert.
14. Analytics freshness: `analytics_daily` stale while `analytics_events` active emits alert.
15. Admin read-only checker tests: command returns all critical invariants without writing.

## Missing monitors/alerts list

| Metric name | Source | Threshold | Severity | Alert text | Owner action | Runbook | False positive risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `webhook_update_processing_failures` | `processed_updates`, outbox | `FAILED > 0` in 15m or spike | P1/P0 if sustained | `Telegram updates failing` | inspect failing update types and worker | retry/review path | low |
| `paid_without_entitlement` | `purchases`, `entitlements`, ledger | any paid premium > N min without effective entitlement/review | P0 | `Paid premium has no entitlement` | open payment review | payment repair runbook | low |
| `paid_uncredited_age_minutes` | `purchases` | `PAID_UNCREDITED > 10m` | P0/P1 | `Paid purchase not credited` | run read-only checker, then approved repair | payment review runbook | low |
| `paid_without_charge_id` | `purchases` | any new paid row missing provider charge | P1 | `Paid purchase missing provider evidence` | mark review, block auto-credit | payment evidence runbook | low |
| `reconciliation_diff_nonzero` | reconciliation checker | any non-zero unexplained diff | P1 | `Payment reconciliation diff` | inspect safe review rows | reconciliation runbook | medium |
| `tournament_invites_expected_vs_sent` | eligible query + delivery attempts | eligible > 0 and sent+failed+skipped = 0 after N min | P1 | `Tournament invites produced no delivery outcomes` | inspect beat/worker and delivery attempts | messaging repair runbook | medium |
| `daily_cup_expected_vs_sent` | cup schedule + delivery attempts | eligible > 0 and zero outcomes | P1 | `Daily Cup messaging zero delivery` | inspect eligibility and Telegram errors | Daily Cup repair runbook | medium |
| `private_tournament_round_delivery_gap` | tournament state + delivery attempts | round started and no outcomes after N min | P1 | `Private tournament round messages missing` | enqueue repair only after approval | tournament repair runbook | low |
| `celery_task_heartbeat_age_seconds` | heartbeat table | task age > 2x schedule interval | P1 | `Critical Celery task stale` | inspect worker/beat | worker incident runbook | low |
| `beat_heartbeat_age_seconds` | heartbeat table | age > 2x shortest critical interval | P1 | `Celery beat stale` | inspect beat container | beat incident runbook | low |
| `queue_oldest_message_age_seconds` | Redis/Celery queue metadata | high queue > 5m, normal > 15m | P1 | `Queue backlog aging` | inspect worker concurrency/errors | queue runbook | medium |
| `telegram_delivery_failure_rate` | delivery attempts | failed / attempts > threshold | P1 | `Telegram delivery failure spike` | inspect 403/429/5xx mix | delivery runbook | medium |
| `telegram_blocked_users_count` | blocked/skipped state | sudden increase or repeated 403 | P2/P1 if mass | `Blocked users spike` | suppress/exclude/recover | blocked-user runbook | medium |
| `streak_update_stale` | `streak_state`, quiz activity | quiz activity exists and no streak update > N hours | P1 | `Streak updates stale` | inspect submit flow/timezone | streak repair runbook | low |
| `leaderboard_stats_stale` | stats aggregation | aggregation older than interval | P2/P1 if visible | `Leaderboard aggregation stale` | rerun after approval | stats runbook | medium |
| `scheduled_offer_zero_delivery` | offers schedule/impressions | eligible > 0 and impressions/delivery = 0 | P2 | `Scheduled offer delivered to nobody` | inspect eligibility/config | offers runbook | medium |
| `auto_recovery_enabled_state` | safe config status endpoint/checker | enabled without explicit rollout | P1 | `Payment auto-recovery enabled` | stop rollout, inspect config | payment config runbook | low |
| `expired_active_entitlements_count` | `entitlements` | any active row with `ends_at <= now()` | P1/P2 | `Expired entitlement still ACTIVE` | run approved expiry cleanup/review | entitlement lifecycle runbook | low |

## Missing recovery/manual repair paths

| Area | Missing path |
| --- | --- |
| Daily Cup invites | repair command that lists expected targets and delivery outcomes, then optionally replays only failed/skipped targets after approval |
| Daily Cup round/final/cancel messages | durable failed/skipped rows plus scoped resend/edit path |
| Private tournament messaging | per-round repair command with tournament id and dry-run first |
| Beaten notifications | delivery attempt table and retry/suppress decision |
| Telegram blocked users | blocked-user marking, suppress policy, unblock detection, dashboard |
| Payment anomalies | live production needs PR #245 evidence/review schema and a no-secrets checker aligned to production commit |
| Premium expiry | expiry transition job or checker plus approved cleanup path |
| Streak/global record | read-only checker and optional aggregation/cache rebuild after approval |
| Worker/beat | heartbeat table and runbook for stale task/queue age |
| Analytics freshness | daily aggregation repair path and alert if dashboard stale |

## Risk ranking

### P0

No active P0 was confirmed during this audit.

Near-P0 risk:
- payment production is behind the merged reliability work and lacks current durable payment evidence/review schema;
- any new payment anomaly in live production may not be captured with the intended PR #245 review state.

### P1

1. Production server is behind `origin/main` and does not include PR #244/#245 payment hardening.
2. Live DB lacks `telegram_update_inbox`, `payment_events`, `payment_reconciliation_reviews`.
3. One credited premium purchase in production lacks `telegram_payment_charge_id`; no active entitlement loss was proven, but reconciliation/refund evidence is incomplete.
4. Daily Cup/tournament message delivery has no durable sent/failed/skipped outcomes.
5. Daily Cup registration push can mark a push as sent before Telegram delivery succeeds.
6. Worker/beat have no durable heartbeat/last-success invariant.
7. Premium entitlement lifecycle has expired `ACTIVE` rows and no clear expiry transition.
8. Telegram delivery failures and blocked users are not centrally persisted/alerted.

### P2

1. Beaten notification delivery failures are not persisted as repair-ready state.
2. Daily Cup cancel/result/reward message failures can be logged/swallowed without durable repair target.
3. Missing failure tests around delivery outcome persistence and messaging invariants.
4. Analytics/dashboard freshness is not a production invariant.
5. Redis/cache staleness monitors are incomplete, especially before deploying current-main global streak cache.
6. Admin/manual repair paths are scattered and not standardized as dry-run first.
7. Local current-main tests were not run in this audit and would not prove current production anyway because production drift exists.

### P3

1. Runbook/docs cleanup.
2. Naming consistency around delivery outcomes.
3. Dashboard polish after the core monitors exist.

## Quick wins на 1 день

1. Add read-only admin/checker command for production invariants: webhook stuck rows, paid without entitlement, paid without charge id, paid-uncredited age, expired active entitlements, Daily Cup/tournament recent state, streak freshness.
2. Add heartbeat table or lightweight heartbeat events for every critical Celery beat task.
3. Alert if `daily_cup_invite_registration_push_sent` or future delivery attempts are zero while eligible users exist.
4. Alert if a Daily Cup starts/round advances but no round/final delivery outcomes exist after N minutes.
5. Alert if `PAID_UNCREDITED` older than 10 minutes or paid premium has no effective entitlement.
6. Alert if Telegram delivery failure rate crosses threshold or 403 blocked-user count spikes.
7. Add one streak update/display test covering `best_streak` global record and Berlin local date.
8. Add one tournament messaging eligibility test that distinguishes `no eligible users` from `eligible users but zero delivery`.

## Fixes на 1 тиждень

1. Deploy/align production intentionally to the merged payment reliability state, including migrations, only under a separate approved deploy task.
2. Introduce generic `telegram_delivery_attempts` or flow-specific delivery tables with `sent|failed|skipped`, reason, correlation id and task name.
3. Wire Daily Cup, private tournament, beaten notification and bulk delivery paths to persist delivery outcomes.
4. Add production invariant checker and scheduled alert task for payments, messaging, worker/beat, queue age, streak and offers.
5. Add repair runbooks/commands for Daily Cup, private tournament, delivery failures and streak/leaderboard aggregation.
6. Add premium expiry transition or cleanup job with tests proving expired `ACTIVE` rows do not block new premium.
7. Add tests for Telegram 403/429 handling and blocked-user suppression.
8. Add analytics freshness checker for monetization dashboards.

## Hardening на 1 місяць

1. Build an operator dashboard for payments, worker/beat heartbeat, queue age, Telegram delivery, Daily Cup/tournaments, streak and offers.
2. Add scheduled audit task that writes daily invariant snapshots and alerts on drift.
3. Define dead-letter queue policy for task failures and payment/messaging review items.
4. Build replay tooling with dry-run, target scoping, idempotency and approval gates.
5. Build admin repair UI/CLI for payment, tournament, Daily Cup, streak and delivery anomalies.
6. Implement Telegram blocked-user lifecycle management.
7. Add end-to-end synthetic tests for webhook, payment, Daily Cup messaging, private tournament messaging and streak.
8. Load test critical messaging flows with realistic Telegram failure simulation.
9. Define scale readiness gates before paid ads: max queue age, heartbeat freshness, delivery success rate, payment invariant zero, dashboard freshness.

## Open questions

1. What exact user/chat/date range reported missing tournament invites? Without target ids, actual Telegram delivery cannot be proven from current data.
2. Should `inline_query` remain in Telegram `allowed_updates`?
3. What is the intended policy for expired `ACTIVE` entitlements: transition to `EXPIRED`, leave stale for history, or repair on read?
4. Which actor owns P1 alert response: product owner, backend operator, or support?
5. Should production be moved to PR #245 immediately, or should a deployment audit happen first because production is three PRs behind?
6. What threshold should define Daily Cup/tournament delivery incident: zero delivery, failure percentage, or no sent messages despite eligible users?
7. Should blocked Telegram users be excluded globally from mass sends or classified per flow?
8. If a specific streak user is suspected, what user id/chat id should be used for user-level reconstruction?

## Evidence appendix

Detailed command and SQL evidence is in `reports/production_runtime_findings_20260710.md`.

Files inspected:
- `.agent/AGENTS.md`;
- `.agent/core/WORK_SCOPE.md`;
- `.agent/core/DEFINITION_OF_DONE.md`;
- `.agent/core/TASK_OUTPUT_FORMAT.md`;
- `.agent/core/AUTO_CHECKLIST.md`;
- `.agent/core/SECURITY_RULES.md`;
- `.agent/core/GIT_WORKFLOW.md`;
- `.agent/core/PRINCIPLES.md`;
- `.agent/project/PROJECT_CONTEXT.md`;
- `.agent/project/CODE_STYLE.md`;
- `app/api/routes/telegram_webhook.py`;
- `app/services/payment_update_evidence.py`;
- `app/workers/celery_app.py`;
- `app/workers/tasks/daily_cup_schedule.py`;
- `app/workers/tasks/daily_cup_async.py`;
- `app/workers/tasks/daily_cup_registration_push.py`;
- `app/workers/tasks/daily_cup_messaging.py`;
- `app/workers/tasks/daily_cup_messaging_delivery.py`;
- `app/workers/tasks/tournaments_async.py`;
- `app/workers/tasks/tournaments_messaging.py`;
- `app/workers/tasks/tournaments_messaging_delivery.py`;
- `app/workers/tasks/payments_reliability.py`;
- `app/workers/tasks/payments_reliability_async.py`;
- `app/workers/tasks/payments_reliability_schedule.py`;
- `app/workers/tasks/telegram_updates_observability.py`;
- `app/workers/tasks/offers_observability.py`;
- `app/economy/streak/service.py`;
- `app/db/repo/users_repo.py`;
- `app/core/global_best_streak_cache.py`;
- `app/economy/purchases/service/credit.py`;
- `app/economy/purchases/service/entitlements.py`;
- `app/db/models/entitlements.py`;
- `app/economy/energy/energy_consume_quiz.py`;
- `app/economy/energy/energy_models.py`;
- `scripts/payment_reliability_checks.py`;
- selected tests listed in `reports/production_runtime_findings_20260710.md`.

Commands run:
- local Git status/branch/HEAD/log/remote checks;
- GitHub connector PR #245 and CI metadata checks;
- public `curl` health/ready checks;
- production SSH read-only Git checks;
- production `docker compose ps`;
- production `docker inspect`;
- production internal `/ready` GET;
- production Celery `inspect ping|active|reserved|scheduled|stats`;
- production Redis `LLEN`, `INFO`, `GET`, `TTL`;
- production `docker logs --since 168h` and read-only grep/count/tail;
- sanitized Telegram `getWebhookInfo`;
- PostgreSQL read-only SQL blocks for schema, tournaments, Daily Cup, analytics, processed updates, outbox, purchases, entitlements, streak and Redis-cache-adjacent checks.

SQL read-only query groups:
- `alembic_version`;
- table/column inventory for critical tables;
- active/stuck tournaments;
- Daily Cup recent state and participant/match/score counts;
- tournament match statuses and round score recency;
- analytics event counts for Daily Cup, duel, payments and streak;
- `processed_updates` status/stuck checks;
- `outbox_events` recent reliability events;
- payment invariant checks: paid-uncredited age, precheckout age, duplicate charge ids, missing charge ids, missing paid timestamps, duplicate active premium, ledger candidates;
- entitlement status/effective-active checks;
- streak aggregate and freshness checks;
- Redis global streak cache key absence checks.

Logs inspected:
- API logs last 7 days;
- worker logs last 7 days;
- beat logs last 7 days;
- searched categories: tournament, Daily Cup, streak, delivery, payment, worker errors, webhook failures.

Test results:
- no local test suite was run in this audit;
- reason: no runtime code was changed, the task was read-only, and local `main` tests cannot prove live behavior while production is behind `main`;
- static test coverage was inspected and mapped above.

Final blocker summary:
- the app is operating at low current load, but P1 reliability invariants are missing;
- advertising/scaling should wait until production is code/schema aligned and critical delivery/payment/worker/streak monitors exist.
