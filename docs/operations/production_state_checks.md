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
curl -sS https://deutchquizarena.de/api/health
```

Expected:
- `api`, `worker`, `beat`, `postgres`, `redis`, `caddy` are `Up`.
- health payload from `/api/health` is `status=ok` and `database/redis/celery=status=ok`.

## 2) Telegram webhook status

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

Expected:
- `url=https://deutchquizarena.de/webhook/telegram`
- `pending_update_count=0` (or low and not growing)
- if `last_error_message` exists, `last_error_date` must be older than current incident window/deploy

## 3) Queue and worker pressure

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

## 4) Error scan (last 30 minutes)

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env logs --since 30m api | \
  grep -Ei "\\[(ERROR|CRITICAL)/|traceback|exception" || true
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env logs --since 30m worker | \
  grep -Ei "\\[(ERROR|CRITICAL)/|traceback|exception|telegram_update_failed_final|telegram_update_non_retryable_error" || true
```

Expected:
- no fresh critical errors,
- no burst of `telegram_update_failed_final`.

## 5) Database lock sanity

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

## 6) Quick usage counters

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

## 7) Escalation triggers

Escalate immediately if any of the following is true:
- health endpoint not `ok`,
- webhook `pending_update_count` grows for more than 10 minutes,
- queue lengths grow continuously with no drain,
- repeated `telegram_update_failed_final`,
- long `idle in transaction` sessions,
- container restart count increases unexpectedly.
