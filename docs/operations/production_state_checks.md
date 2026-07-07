# Production State Checks

Operational checklist for current production runtime.

## 0) Preconditions

```bash
ssh root@deutchquizarena.de
cd /opt/quiz-arena
source /opt/quiz-arena/.env
```

## 1) Runtime and container health

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env ps
bash scripts/check_compose_runtime_consistency.sh --expected-compose-file /opt/quiz-arena/docker-compose.prod.yml
curl -sS https://deutchquizarena.de/health
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env \
  exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2).read().decode())"
```

Expected:
- `api`, `frontend`, `worker`, `beat`, `postgres`, `redis`, `caddy` are `Up`.
- public health payload from `/health` is `status=ok`.
- internal readiness payload from `/ready` is `status=ready` and `database/redis=status=ok`.

## 2) Telegram webhook status

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

Expected:
- `url=https://deutchquizarena.de/webhook/telegram`
- `allowed_updates` contains at least `message`, `callback_query`, and `pre_checkout_query`
- `pending_update_count=0` (or low and not growing)
- if `last_error_message` exists, `last_error_date` must be older than current incident window/deploy

Payment-specific allowed updates check:

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" \
  > /tmp/telegram_webhook_info.json

PYTHONPATH=. .venv/bin/python scripts/payment_reliability_checks.py \
  --skip-db \
  --webhook-info-json /tmp/telegram_webhook_info.json
```

Expected:
- `payments_webhook_allowed_updates_missing` is `OK`.
- `message` is present so Telegram can deliver `message.successful_payment`.
- `pre_checkout_query` is present so Telegram can deliver payment approval requests.
- `callback_query` stays present so existing bot callbacks keep working.

## 3) Payment reliability invariants

```bash
PYTHONPATH=. .venv/bin/python scripts/payment_reliability_checks.py \
  --webhook-info-json /tmp/telegram_webhook_info.json
```

Expected:
- `payments_precheckout_stuck_detected` is `OK`.
- `payments_paid_uncredited_stuck_detected` is `OK`.
- `payments_credited_premium_missing_entitlement` is `OK`.
- `payments_credited_stars_missing_purchase_credit` is `OK`.
- `payments_duplicate_telegram_payment_charge_id` is `OK`.
- `payments_duplicate_active_premium_entitlements` is `OK`.
- `payments_open_manual_review_records` is `OK` or `SKIPPED` if the review table has not been added yet.

Telegram Stars reconciliation review findings currently persist through `outbox_events`
while the dedicated review table migration is deferred:

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"SELECT id, created_at, payload->>'reason' AS reason, payload->>'severity' AS severity, \
        payload->>'transaction_id_hash' AS transaction_id_hash, \
        payload->'candidate_purchase_ids' AS candidate_purchase_ids \
 FROM outbox_events \
 WHERE event_type='payments_telegram_stars_reconciliation_review' AND status='OPEN' \
 ORDER BY created_at DESC, id DESC \
 LIMIT 50;"
```

Expected:
- no `OPEN` rows after a healthy dry-run reconciliation,
- any `OPEN` row is a manual review item before compensation or recovery,
- payload stores hashed transaction identifiers and candidate purchase ids only; it must not
  contain a bot token, raw Telegram payload, raw invoice payload, or raw charge id.

Current limitation:
- outbox review dedupe is best-effort by hashed `review_key` and `OPEN` status;
- it is not protected by a DB-level unique constraint until a dedicated review table/migration is
  approved after a data audit.

Payment invariant alerts are emitted by:

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T worker \
  celery -A app.workers.celery_app inspect registered | grep run_payment_invariant_alerts
```

Expected:
- `app.workers.tasks.payments_reliability.run_payment_invariant_alerts` is registered.
- Alert events route through configured ops channels:
  - `payments_precheckout_stuck_detected`
  - `payments_paid_uncredited_stuck_detected`
  - `payments_credit_invariant_failed`
  - `payments_webhook_allowed_updates_missing`

## 4) Queue and worker pressure

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T redis redis-cli LLEN q_high
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T redis redis-cli LLEN q_normal
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T redis redis-cli LLEN q_low
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T worker celery -A app.workers.celery_app inspect active
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T worker celery -A app.workers.celery_app inspect reserved
```

Expected:
- queue lengths do not grow continuously,
- no long-running stuck tasks in `active`,
- `reserved` remains small.

## 5) Error scan (last 30 minutes)

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env logs --since 30m api | \
  grep -Ei "\\[(ERROR|CRITICAL)/|traceback|exception" || true
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env logs --since 30m worker | \
  grep -Ei "\\[(ERROR|CRITICAL)/|traceback|exception|telegram_update_failed_final|telegram_update_non_retryable_error|payment_recovery_failed" || true
```

Expected:
- no fresh critical errors,
- no burst of `telegram_update_failed_final`.
- no unresolved `payment_recovery_failed` burst.

## 6) Database lock sanity

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
"SELECT pid,state,wait_event_type,wait_event,now()-xact_start AS xact_age,left(query,180) AS query \
 FROM pg_stat_activity \
 WHERE datname=current_database() AND state='idle in transaction' \
 ORDER BY xact_start;"
```

Expected:
- empty set, or only very short-lived entries.

## 7) Quick usage counters

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"SELECT now() AT TIME ZONE 'UTC' AS checked_at_utc, \
        COUNT(*) AS users_total, \
        COUNT(*) FILTER (WHERE last_seen_at >= NOW() - INTERVAL '24 hours') AS users_seen_24h, \
        COUNT(*) FILTER (WHERE last_seen_at >= NOW() - INTERVAL '7 days') AS users_seen_7d \
 FROM users;"
```

Expected:
- query returns quickly,
- values are plausible and not dropping unexpectedly.

## 8) Escalation triggers

Escalate immediately if any of the following is true:
- health endpoint not `ok`,
- webhook `pending_update_count` grows for more than 10 minutes,
- queue lengths grow continuously with no drain,
- repeated `telegram_update_failed_final`,
- any payment reliability invariant check reports `FAIL`,
- any `OPEN` `payments_telegram_stars_reconciliation_review` row exists,
- `payment_recovery_failed` repeats for the same purchase,
- long `idle in transaction` sessions,
- container restart count increases unexpectedly.
