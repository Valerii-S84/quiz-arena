# Production runtime findings 2026-07-10

Статус: read-only evidence log.

Scope: production runtime, Git/GitHub state, Docker/Celery/Redis/PostgreSQL, logs and read-only SQL for critical Quiz Arena flows.

Safety statement:
- no deploy;
- no production DB writes;
- no `.env*` or secrets read/write;
- no migrations;
- no restarts;
- no task replay;
- no manual messaging;
- all production SQL was intended as `BEGIN READ ONLY; SELECT ...; COMMIT;`.

## 1. Local Git and GitHub state

| Check | Evidence | Result |
| --- | --- | --- |
| Local branch | `git rev-parse --abbrev-ref HEAD` | `main` |
| Local HEAD | `git rev-parse HEAD` | `bafcf2730211355e66718d3dbb43b94e69424bca` |
| Local status before report files | `git status --short` | `?? reports/payment_reliability_plan_20260707.md` |
| Recent local commits | `git log --oneline -5` | `bafcf27 Complete payment reliability plan (#245)`, `7256686 fix(payments): complete payment reliability hardening (#244)`, `75d8e7e feat(arena): improve monetization moments and load capacity (#243)`, `1fb8a09 add website visitor analytics`, `8df73c0 fix(energy): slow free energy regeneration (#241)` |
| Remote main | `git ls-remote origin refs/heads/main` | `bafcf2730211355e66718d3dbb43b94e69424bca` |
| PR #245 metadata | GitHub connector `_get_pr_info` | merged `2026-07-10T12:00:32Z`, base `main`, base SHA `72566862...`, head SHA `a12bd155...`, merge commit `bafcf2730211355e66718d3dbb43b94e69424bca` |
| PR #245 CI | GitHub connector `_fetch_commit_workflow_runs` for head `a12bd155...` | workflow run `29087110146`, status `completed`, conclusion `success` |
| `gh` CLI | `gh pr view 245 ...` | failed because local `gh` was not authenticated |

Verdict: local `main` and `origin/main` include PR #245 merge commit `bafcf27`; production does not.

## 2. Production server/runtime state

Host: `root@deutchquizarena.de`.

Application path: `/opt/quiz-arena`.

| Check | Evidence | Result |
| --- | --- | --- |
| Public health | `curl -fsS https://deutchquizarena.de/health` | `{"status":"ok"}` |
| Public ready | `curl -i -sS https://deutchquizarena.de/api/ready` | HTTP `404`; this matches previous production edge behavior where public `/api/ready` is blocked |
| Server repo path | `ssh root@deutchquizarena.de 'cd /opt/quiz-arena && pwd'` | `/opt/quiz-arena` |
| Server branch | `git rev-parse --abbrev-ref HEAD` on server | `main` |
| Server HEAD | `git rev-parse HEAD` on server | `1fb8a096b625ac6955c5a332467ba4291a3d467e` |
| Server recent commits | `git log --oneline -5` on server | `1fb8a09 add website visitor analytics`, `8df73c0 fix(energy): slow free energy regeneration (#241)`, `8de9d27 fix(promo): guard promo callback source (#240)`, `de66759 fix(promo): ignore stale reply context (#239)`, `0ccda1b Fix channel bonus checks and analytics KPI rates (#238)` |
| Server git status | `git status --short` on server | `?? backup_pre_website_analytics_20260604_184020.sql`, `?? manual_compensation_exports/` |
| Runtime drift | compare local/origin `bafcf27` vs server `1fb8a09` | production is behind PR #243, #244 and #245 |

Production drift impact:
- live production does not include payment PR #244/#245 reliability hardening;
- live production DB does not have the new PR #245 payment inbox/review schema;
- any local current-main test evidence for these payment improvements is not proof that production currently has them.

## 3. Docker, uptime, health and queues

Commands:
- `ssh root@deutchquizarena.de 'cd /opt/quiz-arena && docker compose -f docker-compose.prod.yml ps'`
- `ssh root@deutchquizarena.de 'docker inspect --format ... quiz-arena-api-1 quiz-arena-worker-1 quiz_arena_beat_prod quiz_arena_postgres_prod quiz_arena_redis_prod quiz-arena-frontend-1'`
- `ssh root@deutchquizarena.de 'docker exec quiz-arena-api-1 python - <<PY ... GET /ready ... PY'`

Runtime evidence:

| Container | State | Started | Restart count | Health |
| --- | --- | --- | --- | --- |
| `/quiz-arena-api-1` | running | `2026-06-29T10:54:27Z` | `0` | `healthy` |
| `/quiz-arena-worker-1` | running | `2026-06-29T10:54:27Z` | `0` | none |
| `/quiz_arena_beat_prod` | running | `2026-06-29T10:54:27Z` | `0` | none |
| `/quiz_arena_postgres_prod` | running | `2026-06-29T10:54:27Z` | `0` | `healthy` |
| `/quiz_arena_redis_prod` | running | `2026-06-29T10:54:27Z` | `0` | `healthy` |
| `/quiz-arena-frontend-1` | running | `2026-06-29T10:54:27Z` | `0` | none |

Internal API readiness:

```json
{"status":"ready","checks":{"database":{"status":"ok"},"redis":{"status":"ok"}}}
```

Celery commands:
- `docker exec quiz-arena-worker-1 celery -A app.workers.celery_app inspect ping`
- `docker exec quiz-arena-worker-1 celery -A app.workers.celery_app inspect active`
- `docker exec quiz-arena-worker-1 celery -A app.workers.celery_app inspect reserved`
- `docker exec quiz-arena-worker-1 celery -A app.workers.celery_app inspect scheduled`
- `docker exec quiz-arena-worker-1 celery -A app.workers.celery_app inspect stats`

Celery evidence:
- `ping`: one worker node online.
- `active`: empty.
- `reserved`: empty.
- `scheduled`: empty.
- `stats.uptime`: `956507` seconds at inspection time.
- Important task total counters over worker uptime:
  - `process_telegram_update`: `2688`;
  - `run_telegram_updates_reliability_alerts`: `3189`;
  - `run_private_tournament_rounds`: `3189`;
  - `daily_cup.advance_rounds`: `15943`;
  - `daily_cup.close_registration_and_start`: `11`;
  - `daily_cup.publish_final_results`: `11`;
  - `daily_cup.run_daily_cup_round_messaging`: `4`;
  - `daily_cup.send_invite_registration`: `11`;
  - `daily_cup.send_last_call_reminder`: `11`;
  - `daily_cup.send_prestart_reminder`: `11`;
  - `daily_cup.send_turn_reminders`: `1595`;
  - payment reliability tasks were present and had counters, including reconciliation/recovery/rollback tasks;
  - `offers_observability.run_offers_funnel_alerts`: `1063`.

Redis commands:
- `docker exec quiz_arena_redis_prod redis-cli -n 0 LLEN q_high`
- `docker exec quiz_arena_redis_prod redis-cli -n 0 LLEN q_normal`
- `docker exec quiz_arena_redis_prod redis-cli -n 0 LLEN q_low`
- `docker exec quiz_arena_redis_prod redis-cli INFO keyspace`
- `docker exec quiz_arena_redis_prod redis-cli INFO stats`

Redis evidence:
- `q_high`: `0`;
- `q_normal`: `0`;
- `q_low`: `0`;
- `db0`: `keys=4,expires=0`;
- `db1`: `keys=5,expires=0`;
- `db2`: `keys=7377,expires=7377`;
- `rejected_connections=0`;
- `evicted_keys=0`;
- `total_error_replies=1`.

Runtime verdict:
- API/PostgreSQL/Redis are healthy.
- worker and beat are running with no restarts.
- queues are empty.
- Celery counters prove periodic tasks have executed since worker start.
- missing invariant: there is no durable per-task heartbeat table/log evidence proving last execution timestamps and alerting if a task stops.

## 4. Telegram webhook state

Command:
- sanitized read-only `getWebhookInfo` via production environment; token value was not printed.

Allowed safety scope:
- only `getWebhookInfo`;
- no `setWebhook`, `deleteWebhook`, `sendMessage`, `getUpdates`;
- no raw bot token output.

Sanitized result:

```json
{
  "ok": true,
  "url": "https://deutchquizarena.de/webhook/telegram",
  "pending_update_count": 0,
  "last_error_date": null,
  "last_error_message": null,
  "allowed_updates": ["message", "inline_query", "callback_query", "pre_checkout_query"]
}
```

Webhook verdict:
- required update types `message`, `callback_query`, `pre_checkout_query` are enabled;
- there is no Telegram-side pending backlog;
- no Telegram-side last error is reported;
- `inline_query` is also enabled, which is not itself a failure but should be intentional.

## 5. Production logs

Commands:
- `docker logs --since 168h quiz-arena-worker-1`
- `docker logs --since 168h quiz_arena_beat_prod`
- `docker logs --since 168h quiz-arena-api-1`
- greps for `tournament`, `daily_cup`, `streak`, `leaderboard`, `payment`, `delivery`, `worker`, `ERROR`, `CRITICAL`, `Traceback`, `telegram_webhook_invalid_secret`, `telegram_update_failed_final`, `telegram_update_retry_scheduled`.

Evidence:
- worker logs over last 7 days: `0` lines;
- beat logs over last 7 days: `0` lines;
- API logs over last 7 days contain many successful `POST /webhook/telegram 200 OK`;
- `telegram_webhook_invalid_secret`: `170` occurrences over last 7 days;
- API `ERROR|CRITICAL|Traceback|Exception`: `0`;
- API `telegram_webhook_enqueue_failed|telegram_update_failed_final|telegram_update_non_retryable_error|telegram_update_retry_scheduled`: no matching log output;
- payment fail/error/precheckout/success/refund markers in API logs: no matching output.

Log verdict:
- no runtime error pattern was found in API logs;
- worker/beat log files are not useful for 7-day incident reconstruction because they are empty;
- current production observability cannot prove sent/failed/skipped outcomes from logs for Daily Cup/tournament mass delivery.

## 6. Read-only PostgreSQL evidence

All SQL blocks were intended to run as:

```sql
BEGIN READ ONLY;
SELECT ...;
COMMIT;
```

One early inline SQL attempt failed due shell quoting before a query ran; the checks were then rerun through heredoc read-only blocks.

### 6.1 Schema and migration state

Queries:
- `SELECT version_num FROM alembic_version;`
- `SELECT table_name FROM information_schema.tables WHERE table_schema='public' ...;`
- `SELECT column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_name IN (...);`

Evidence:
- production Alembic version: `9b8c7d6e5f4a`;
- key tables present: `entitlements`, `offers_impressions`, `outbox_events`, `processed_updates`, `purchases`, `streak_state`, `tournament_matches`, `tournament_participants`, `tournament_round_scores`, `tournaments`;
- key PR #245 tables absent in production: `telegram_update_inbox`, `payment_events`, `payment_reconciliation_reviews`.

### 6.2 Tournament and Daily Cup state

Queries:
- type/status count from `tournaments`;
- recent `DAILY_ARENA` rows with participants/matches/scores;
- active/stuck tournament rows excluding terminal statuses;
- match status counts;
- round score counts.

Evidence:
- tournament status by type:
  - `DAILY_ARENA CANCELED`: `92`, last created `2026-07-09 14:00:00.011779+00`;
  - `DAILY_ARENA COMPLETED`: `38`, last created `2026-06-29 14:00:00.00479+00`;
  - `PRIVATE CANCELED`: `6`, last created `2026-03-07 15:37:46.245092+00`.
- recent Daily Arena:
  - `2026-07-09`: `CANCELED`, participants `3`, matches `0`, scores `0`;
  - `2026-07-08`: `CANCELED`, participants `1`;
  - `2026-07-07`: `CANCELED`, participants `1`;
  - `2026-07-06`: `CANCELED`, participants `2`;
  - `2026-07-05`: `CANCELED`, participants `3`;
  - `2026-07-04`: `CANCELED`, participants `3`;
  - `2026-07-03`: `CANCELED`, participants `0`;
  - `2026-07-02`: `CANCELED`, participants `1`;
  - `2026-07-01`: `CANCELED`, participants `2`;
  - `2026-06-30`: `CANCELED`, participants `2`;
  - `2026-06-29`: `COMPLETED`, participants `4`, matches `6`, scores `12`.
- open/stuck tournaments: `0`;
- tournament match statuses:
  - `COMPLETED`: `54`, last deadline `2026-06-28 16:26:55+00`;
  - `WALKOVER`: `254`, last deadline `2026-06-29 16:30:00+00`;
- `tournament_round_scores` latest rows are from `2026-06-29`.

Verdict:
- no active stuck tournament was found;
- Daily Arena round messages after `2026-06-29` were not expected because cups were canceled below the minimum participant threshold;
- actual Telegram delivery of invites cannot be proven from current production tables/logs.

### 6.3 Analytics events for Daily Cup, tournament and monetization

Queries:
- `analytics_events` grouped by event name for last 30 days;
- Daily Cup events by day for last 14 days;
- payment and arena event counts.

Evidence:
- Daily Cup push/lifecycle last 30 days:
  - `daily_cup_invite_registration_push_sent`: `1288`, last `2026-07-09 14:00:00`;
  - `daily_cup_last_call_reminder_sent`: `1252`, last `2026-07-09 14:30:00`;
  - `daily_cup_prestart_reminder_sent`: `1228`, last `2026-07-09 14:50:00`;
  - `daily_cup_canceled`: `22`, last `2026-07-09 15:00:00`;
  - `daily_cup_started`: `8`, last `2026-06-29 15:00:00`;
  - `daily_cup_round_started`: `24`, last `2026-06-29 16:00:00`;
  - `daily_cup_match_completed`: `60`, last `2026-06-29 16:30:00`;
  - `daily_cup_turn_reminder_sent`: `163`, last `2026-06-29 16:20:00`.
- Daily Cup invite push events exist every day through `2026-07-09`.
- Important caveat: the code writes `daily_cup_*_push_sent` analytics before the Telegram send, so this is not durable delivery proof.
- Arena/duel events:
  - `arena_duel_created`: `21`, last `2026-07-08 18:49`;
  - `arena_duel_completed`: `23`, last `2026-07-08 18:52`;
  - `duel_paywall_shown`: `25`, last `2026-07-08 19:51`;
  - `arena_result_beaten_notification_sent`: `1`, last `2026-07-01 08:36`.
- Payment analytics:
  - `purchase_credited`: `63`, last `2026-07-10 10:12`;
  - `purchase_paid_uncredited`: `63`, last `2026-07-10 10:12`;
  - `purchase_init_created`: `13`, last `2026-07-07`;
  - `purchase_invoice_sent`: `13`, last `2026-07-07`;
  - `purchase_precheckout_ok`: `2`, last `2026-07-02`.

Verdict:
- analytics prove task code emitted events;
- analytics do not prove Telegram delivery;
- there is no durable sent/failed/skipped delivery table for tournament/Daily Cup mass messages.

### 6.4 Processed Telegram updates and outbox

Queries:
- status counts from `processed_updates`;
- stuck `PROCESSING` rows older than 5 minutes;
- recent `outbox_events`.

Evidence:
- `processed_updates`:
  - `PROCESSED`: `3534`, first `2026-06-26`, last `2026-07-10 12:32:31`;
  - `FAILED`: `1`, last `2026-07-02 11:37:36`;
  - last 24h: `166` processed;
  - stuck processing older than 5m: `0`.
- `outbox_events` last 30 days:
  - `telegram_update_failed_final`: `SENT` `4`, last `2026-07-02 11:37:36`;
  - `telegram_update_retry_scheduled`: `SENT` `28`, last `2026-07-02 11:36:20`;
  - no tournament/daily/payment/delivery outbox rows were found.

Verdict:
- webhook update processing currently has durable idempotency/failed markers at update level;
- payment-specific inbox/review schema from current main is not in production;
- tournament/daily delivery result persistence is missing.

### 6.5 Payment invariants

Queries:
- purchase status counts by product type;
- paid-uncredited older than 10 minutes;
- precheckout older than 30 minutes;
- credited purchases without ledger candidate;
- active premium entitlements and stale expired active rows;
- duplicate charge IDs;
- missing charge IDs and missing paid timestamps.

Evidence:
- purchase status counts:
  - `CREDITED MICRO`: `140`, last credited `2026-07-10 10:12`;
  - `CREDITED PREMIUM`: `4`, last created `2026-07-02`, last credited `2026-07-07 17:22:41`;
  - `FAILED MICRO`: `47`;
  - `FAILED PREMIUM`: `14`.
- `paid_uncredited_10m`: `0`;
- `precheckout_ok_30m`: `0`;
- `credited_without_ledger_candidate`: `0`;
- duplicate Telegram charge ID: `0`;
- duplicate effective active premium entitlements: `0`;
- paid purchase missing `paid_at`: `0`;
- paid purchase missing `telegram_payment_charge_id`: `1`;
- details for missing charge ID:
  - status `CREDITED`;
  - product `PREMIUM_WEEK`;
  - created `2026-07-02`;
  - paid `2026-07-02 11:35:06`;
  - credited `2026-07-07 17:22:41`;
  - no refund;
  - effective entitlement exists, so this is not active entitlement loss, but it is a reconciliation/refund evidence gap.
- entitlements:
  - `PREMIUM ACTIVE`: `3`;
  - `PREMIUM EXPIRED`: `1`;
  - effective active premium count: `2`;
  - `PREMIUM_STARTER ACTIVE is_expired=true`: `1`;
  - `PREMIUM_WEEK ACTIVE is_expired=false`: `1`;
  - `PREMIUM_MONTH ACTIVE is_expired=false`: `1`;
  - `PREMIUM_WEEK EXPIRED is_expired=true`: `1`.

Verdict:
- no stale paid-uncredited production purchase was found;
- no current active entitlement loss was proven;
- one paid/credited premium row lacks provider charge evidence;
- at least one expired entitlement still has status `ACTIVE`;
- production lacks PR #245 review tables that would make these anomalies first-class review state.

### 6.6 Daily streak and global record

Queries:
- aggregate from `streak_state`;
- users with current/best streak above thresholds;
- `today_status` distribution;
- Redis `GET/TTL quiz_arena:global_best_streak` in db0/db1/db2.

Evidence:
- `streak_state` rows: `469`;
- `max_current_streak`: `33`;
- `max_best_streak`: `87`;
- latest `updated_at`: `2026-07-10 12:32:31`;
- latest `last_activity_local_date`: `2026-07-10`;
- current streak `>=80`: `0`;
- best streak `>=80`:
  - best `87`: one user, last updated `2026-07-02 11:37:48`, last activity `2026-07-02`;
  - best `80`: one user, last updated `2026-07-10 08:22:20`, last activity `2026-07-10`;
- users with `current_streak > 87`: `0`;
- users with `best_streak > 87`: `0`;
- `today_status`: `NO_ACTIVITY 237`, `PLAYED 232`;
- Redis key `quiz_arena:global_best_streak`:
  - db0: absent;
  - db1: absent;
  - db2: absent.

Production code evidence:
- server commit `1fb8a09` reads global best from DB, not from the newer cache module;
- current main has `app/core/global_best_streak_cache.py`, but that code is not deployed.

Verdict:
- global `Rekord 87` is expected behavior from production DB state;
- streak updates are not globally frozen because records were updated on `2026-07-10`;
- if the report concerns a specific user’s personal current streak, user-specific evidence is still needed.

## 7. Code/test evidence summary

Code/test inspection was local read-only on `main` at `bafcf27`, so it reflects current repository state, not live production `1fb8a09`.

Important code surfaces inspected:
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
- `scripts/payment_reliability_checks.py`.

Important tests inspected:
- `tests/api/test_telegram_webhook.py`;
- `tests/workers/test_telegram_updates_task.py`;
- `tests/bot/test_payments_handler_flow.py`;
- `tests/bot/test_payments_successful_checkpoint_units.py`;
- `tests/economy/test_purchase_successful_payment_validation_units.py`;
- `tests/integration/test_purchase_premium_integration.py`;
- `tests/integration/test_economy_invariants_b_refund_symmetry_integration.py`;
- `tests/workers/test_telegram_stars_reconciliation_task.py`;
- `tests/workers/test_worker_schedule_units.py`;
- `tests/workers/test_daily_cup_registration_push_units.py`;
- `tests/workers/test_daily_cup_turn_reminder_worker.py`;
- `tests/workers/test_tournament_task_entrypoints_units.py`;
- `tests/workers/test_worker_coverage_last_points.py`;
- `tests/workers/test_arena_duels_notifications.py`;
- `tests/services/test_global_best_streak_cache.py`;
- `tests/services/test_offers_observability.py`;
- `tests/integration/test_analytics_daily_aggregation_integration.py`.

Local tests were not run in this audit. Reason: the requested work was audit-only, no runtime code was changed, and local current-main tests would not prove live production behavior because production is behind `main`.
