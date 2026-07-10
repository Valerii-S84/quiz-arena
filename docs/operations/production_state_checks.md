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

Payment reliability flags must stay safe/off unless a separate owner-approved dry-run or
auto-recovery window is active:

```bash
printf 'TELEGRAM_STARS_RECONCILIATION_ENABLED=%s\n' "${TELEGRAM_STARS_RECONCILIATION_ENABLED:-false}"
printf 'TELEGRAM_STARS_RECONCILIATION_DRY_RUN=%s\n' "${TELEGRAM_STARS_RECONCILIATION_DRY_RUN:-true}"
printf 'TELEGRAM_STARS_AUTO_RECOVERY_ENABLED=%s\n' "${TELEGRAM_STARS_AUTO_RECOVERY_ENABLED:-false}"
```

Expected default-safe values:
- `TELEGRAM_STARS_RECONCILIATION_ENABLED=false`.
- `TELEGRAM_STARS_RECONCILIATION_DRY_RUN=true`.
- `TELEGRAM_STARS_AUTO_RECOVERY_ENABLED=false`.

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
- `payments_constraint_duplicate_premium_source_purchase` is `OK`.
- `payments_constraint_duplicate_purchase_credit_ledger` is `OK`.
- `payments_constraint_paid_purchase_missing_charge_id` is `OK`.
- `payments_constraint_paid_purchase_missing_paid_at` is `OK`.
- `payments_constraint_credited_purchase_missing_credited_at` is `OK`.
- `payments_constraint_credited_purchase_missing_credited_at` is strict for `CREDITED` rows and
  for `REFUNDED` rows with credit evidence. It intentionally allows `REFUNDED` rows with
  `credited_at IS NULL` when the purchase was refunded from `PAID_UNCREDITED` before any product or
  entitlement was granted.
- `payments_open_manual_review_records` is `OK`.

DB constraint hardening rule:
- do not add strict Alembic constraints during an incident or without owner approval;
- run this read-only checker first and require every `payments_constraint_*` preflight to be `OK`;
- only then consider a backward-compatible migration for unique premium entitlement per source
  purchase, unique purchase credit ledger per purchase, or stricter paid-status invariants. Any
  future `credited_at` constraint must preserve the uncredited refund exception.

Open review findings перевіряються у двох місцях:
- Telegram Stars reconciliation reviews ще використовують legacy `outbox_events`.
- strict payment validation failures використовують dedicated `payment_reconciliation_reviews`.

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"SELECT id, created_at, payload->>'reason' AS reason, payload->>'severity' AS severity, \
        payload->>'transaction_id_hash' AS transaction_id_hash, \
        payload->>'transaction_amount' AS transaction_amount, \
        payload->>'transaction_date' AS transaction_date, \
        payload->>'telegram_user_id' AS telegram_user_id, \
        payload->'candidate_purchase_ids' AS candidate_purchase_ids \
 FROM outbox_events \
 WHERE event_type='payments_telegram_stars_reconciliation_review' AND status='OPEN' \
 ORDER BY created_at DESC, id DESC \
 LIMIT 50;"
```

Expected:
- немає `OPEN` legacy reconciliation rows після здорового dry-run reconciliation,
- будь-який `OPEN` row є manual review item до compensation, recovery або refund action,
- payload stores hashed transaction identifiers, amount/date/user clues, and candidate purchase
  ids only; it must not contain a bot token, raw Telegram payload, raw invoice payload, or raw
  charge id.

Dedicated payment validation reviews:

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"SELECT id, created_at, review_type, severity, reason, purchase_id, transaction_id_hash, \
        safe_payload->>'telegram_payment_charge_id_hash' AS payment_charge_hash, status \
 FROM payment_reconciliation_reviews \
 WHERE status='OPEN' \
 ORDER BY created_at DESC, id DESC \
 LIMIT 50;"
```

Expected:
- немає `OPEN` rows після здорового Stars purchase smoke,
- rows містять тільки hashes і safe purchase/user references,
- `OPEN` row блокує automatic credit/recovery до owner review.

Поточне обмеження для legacy Stars reconciliation reviews:
- outbox review dedupe is best-effort by hashed `review_key` and `OPEN` status;
- `OPEN` review rows excluded from retention cleanup, тому unresolved payment discrepancies не
  age out silently. Нові payment validation reviews використовують dedicated review table з
  unique key.

Payment-relevant webhook updates durably captured до enqueue/ACK через `telegram_update_inbox` і
`payment_events`:

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"SELECT update_id, received_at, update_kind, status, \
        sanitized_evidence->>'payment_update_kind' AS payment_update_kind, payload_hash \
 FROM telegram_update_inbox \
 ORDER BY received_at DESC, update_id DESC \
 LIMIT 50;"
```

Expected:
- recent payment smoke updates мають inbox row до normal worker processing,
- `payment_update_kind` is one of `pre_checkout_query`, `message.successful_payment`, or
  `message.refunded_payment`,
- `message.refunded_payment` updates are handled by the payments router through the idempotent
  purchase refund path after enqueue,
- evidence зберігає тільки sanitized fields і hashes. Не можна зберігати raw order info, email,
  phone, shipping details, raw charge ids, request headers або webhook secrets.

Payment event evidence:

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"SELECT id, provider, event_type, invoice_payload, provider_charge_id_hash, \
        currency, total_amount, source_inbox_update_id \
 FROM payment_events \
 ORDER BY created_at DESC, id DESC \
 LIMIT 50;"
```

Expected:
- duplicate webhook delivery не створює duplicate event rows,
- `provider_charge_id_hash` заповнений, коли provider charge evidence існує,
- raw charge ids і raw Telegram payment payloads відсутні.

Auto-recovery success evidence, if an owner-approved non-dry-run window was active, is written as
`payments_telegram_star_auto_recovered`:

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"SELECT id, created_at, payload->>'purchase_id' AS purchase_id, \
        payload->>'transaction_id_hash' AS transaction_id_hash, payload->>'classification' AS classification \
 FROM outbox_events \
 WHERE event_type='payments_telegram_star_auto_recovered' \
 ORDER BY created_at DESC, id DESC \
 LIMIT 50;"
```

Expected:
- normally no recent rows while reconciliation is disabled or dry-run,
- any row contains only `purchase_id`, a hashed transaction id, and classification metadata.

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
- any `OPEN` `payment_reconciliation_reviews` row exists,
- `payment_recovery_failed` repeats for the same purchase,
- a non-dry-run reconciliation window is active without owner approval,
- long `idle in transaction` sessions,
- container restart count increases unexpectedly.

Payment reliability rollback:
- set `TELEGRAM_STARS_RECONCILIATION_ENABLED=false`,
- keep `TELEGRAM_STARS_RECONCILIATION_DRY_RUN=true`,
- set `TELEGRAM_STARS_AUTO_RECOVERY_ENABLED=false`,
- restart only the approved app services for the target environment,
- schema rollback є окремим owner-approved release rollback рішенням; перша operational response
  вимикає reconciliation/auto-recovery flags, а не мутує production data.
