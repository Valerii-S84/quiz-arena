# First Deploy And Rollback (VPS)

## 1) DNS and host prep
1. Buy/prepare VPS with Docker Engine + Compose plugin.
2. Point DNS `A` record:
   - `deutchquizarena.de` -> `<server_public_ip>`
3. Open ports on firewall/security group:
   - `22/tcp` (SSH)
   - `80/tcp` (HTTP)
   - `443/tcp` (HTTPS)

## 2) Copy code and bring stack up
From local repo:

```bash
scripts/deploy.sh <user@server_ip> /opt/quiz-arena
```

On server set production secrets:

```bash
cd /opt/quiz-arena
nano .env
```

Mandatory to change:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `INTERNAL_API_TOKEN`
- `INTERNAL_API_ALLOWLIST` (CIDR list for ops/internal access, not localhost in production)
- `INTERNAL_API_TRUSTED_PROXIES` (reverse-proxy CIDRs that are allowed to set forwarded client IP)
- `PROMO_SECRET_PEPPER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL` password segment
- `CADDY_EMAIL`

If API is behind reverse proxy/load balancer:
- set `INTERNAL_API_TRUSTED_PROXIES` to proxy network(s), for example `10.0.0.0/8,172.16.0.0/12`;
- set `INTERNAL_API_ALLOWLIST` to real operator/source network(s), for example VPN egress CIDRs.

Re-apply:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Scale runtime services (example):
```bash
docker compose -f docker-compose.prod.yml up -d --scale api=2 --scale worker=3
```

Capacity guardrails before scaling:
- DB connections scale with `API_WORKERS * api_replicas` (each API process has its own SQLAlchemy pool). Increase gradually and monitor Postgres `max_connections`.
- Task pressure scales with `CELERY_WORKER_CONCURRENCY * worker_replicas`. For DB-heavy workloads, increase worker replicas/concurrency step-by-step and monitor DB saturation.

Note:
- `scripts/deploy.sh` now runs both DB migrations and mandatory QuizBank import (`python -m scripts.quizbank_import_tool --replace-all`) before bringing up `api/worker/beat/caddy`.
- Deploy now includes an automatic gate `python -m scripts.quizbank_assert_non_empty`; deploy fails immediately if `quiz_questions` is empty.
- If you deploy manually (without `scripts/deploy.sh`), run this import step explicitly after migrations.

## 3) Webhook setup
Run on server or local machine:

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=https://deutchquizarena.de/webhook/telegram" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"
```

Check:

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

## 4) Smoke checks
- API health:
```bash
curl -sS https://deutchquizarena.de/health
```
- Containers:
```bash
docker compose -f docker-compose.prod.yml ps
```
- Logs:
```bash
docker compose -f docker-compose.prod.yml logs --tail=100 api worker beat
```
- Verify Docker hardening (non-root + non-editable install + image size):
```bash
docker compose -f docker-compose.prod.yml exec -T api id
docker compose -f docker-compose.prod.yml exec -T api python -c "import app; print(app.__file__)"
docker image ls --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep -E "quizarena-|REPOSITORY"
```
- Verify ops_ui static assets are present in runtime image:
```bash
docker compose -f docker-compose.prod.yml exec -T api python -c "import app; from pathlib import Path; p = Path(app.__file__).parent / 'ops_ui' / 'site' / 'static'; print(p, 'exists=', p.exists())"
```
- Verify celery beat schedule is persisted in `/tmp`:
```bash
docker compose -f docker-compose.prod.yml exec -T beat sh -lc "ls -l /app/celerybeat-schedule /tmp/celerybeat-schedule*"
```
- Verify quiz content loaded:
```bash
docker compose -f docker-compose.prod.yml run --rm api python - <<'PY'
import asyncio
from sqlalchemy import select, func
from app.db.models.quiz_questions import QuizQuestion
from app.db.session import SessionLocal


async def main() -> None:
    async with SessionLocal() as session:
        total = (await session.execute(select(func.count()).select_from(QuizQuestion))).scalar_one()
        print(f"quiz_questions_total={total}")
        raise SystemExit(0 if total > 0 else 1)


asyncio.run(main())
PY
```

## 5) Telegram update reliability (P0-1)
Default knobs in `.env` (tune only if needed):
- `TELEGRAM_UPDATE_PROCESSING_TTL_SECONDS=300`
- `TELEGRAM_UPDATE_TASK_MAX_RETRIES=7`
- `TELEGRAM_UPDATE_TASK_RETRY_BACKOFF_MAX_SECONDS=300`
- `TELEGRAM_UPDATES_ALERT_WINDOW_MINUTES=15`
- `TELEGRAM_UPDATES_STUCK_ALERT_MIN_MINUTES=10`
- `TELEGRAM_UPDATES_RETRY_SPIKE_THRESHOLD=25`
- `TELEGRAM_UPDATES_FAILED_FINAL_SPIKE_THRESHOLD=3`
- `TELEGRAM_UPDATES_OBSERVABILITY_TOP_STUCK_LIMIT=10`

What is monitored every 5 minutes (beat task):
- `processed_updates_processing_stuck_count`
- `processed_updates_processing_age_max_seconds`
- `telegram_updates_reclaimed_total`
- `telegram_updates_retries_total`
- `telegram_updates_failed_final_total`

Alert event:
- `telegram_updates_reliability_degraded`

Quick DB verification on server:
```bash
docker compose -f docker-compose.prod.yml run --rm api python - <<'PY'
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from app.db.models.processed_updates import ProcessedUpdate
from app.db.models.outbox_events import OutboxEvent
from app.db.session import SessionLocal

EVENTS = (
    "telegram_update_reclaimed",
    "telegram_update_retry_scheduled",
    "telegram_update_failed_final",
)

async def main() -> None:
    now_utc = datetime.now(timezone.utc)
    since_utc = now_utc - timedelta(minutes=15)
    async with SessionLocal() as session:
        stuck_count = (
            await session.execute(
                select(func.count(ProcessedUpdate.update_id)).where(
                    ProcessedUpdate.status == "PROCESSING",
                    ProcessedUpdate.processed_at <= now_utc - timedelta(minutes=10),
                )
            )
        ).scalar_one()
        by_type_rows = (
            await session.execute(
                select(OutboxEvent.event_type, func.count(OutboxEvent.id))
                .where(
                    OutboxEvent.created_at >= since_utc,
                    OutboxEvent.event_type.in_(EVENTS),
                )
                .group_by(OutboxEvent.event_type)
            )
        ).all()
    print("processed_updates_processing_stuck_count=", int(stuck_count))
    print("outbox_events_15m_by_type=", {str(k): int(v) for k, v in by_type_rows})

asyncio.run(main())
PY
```

## 6) Backups (minimum)
Daily Postgres dump (cron example):

```bash
docker exec -t quiz_arena_postgres_prod pg_dump -U quiz -d quiz_arena -Fc > /var/backups/quiz_arena_$(date +%F).dump
```

## 7) Rollback
If deploy is broken after new commit:

1. On server, switch to previous git commit/tag.
2. Rebuild and restart:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
3. If migration is backward-incompatible, restore last DB dump:
```bash
pg_restore -U quiz -d quiz_arena --clean --if-exists /var/backups/<last_good_dump>.dump
```

## 8) Notes
- Keep `.env` only on server, never commit.
- Apply migrations before exposing webhook after schema changes.
- For first production launch, prefer clean DB init instead of local dump import (current local data is dev/smoke level).
