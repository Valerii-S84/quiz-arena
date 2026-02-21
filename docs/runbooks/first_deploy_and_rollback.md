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
- `PROMO_SECRET_PEPPER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL` password segment
- `CADDY_EMAIL`

Re-apply:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

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

## 5) Backups (minimum)
Daily Postgres dump (cron example):

```bash
docker exec -t quiz_arena_postgres_prod pg_dump -U quiz -d quiz_arena -Fc > /var/backups/quiz_arena_$(date +%F).dump
```

## 6) Rollback
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

## 7) Notes
- Keep `.env` only on server, never commit.
- Apply migrations before exposing webhook after schema changes.
- For first production launch, prefer clean DB init instead of local dump import (current local data is dev/smoke level).
