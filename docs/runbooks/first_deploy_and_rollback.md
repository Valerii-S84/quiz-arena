# First Deploy And Rollback (VPS)

This runbook is only for:
- first production launch,
- emergency rollback.

For routine releases after initial setup, use:
- `docs/runbooks/github_to_prod_safe_deploy.md`

## 1) Pre-flight (one-time)

1. Prepare VPS with Docker Engine + Compose plugin.
2. Point DNS:
   - `deutchquizarena.de` -> `<server_public_ip>`
3. Open firewall ports:
   - `22/tcp`, `80/tcp`, `443/tcp`

Quick checks:

```bash
dig +short deutchquizarena.de
ssh root@<SERVER_IP> "docker --version && docker compose version"
```

## 2) Initial code bootstrap

From local repo:

```bash
scripts/deploy.sh <user@server_ip> /opt/quiz-arena
```

What this does:
- syncs repository files to `/opt/quiz-arena`,
- builds runtime images,
- runs migrations,
- imports QuizBank,
- runs post-deploy gate.

## 3) Set real production secrets

On server:

```bash
cd /opt/quiz-arena
nano .env
```

Mandatory to set:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `INTERNAL_API_TOKEN`
- `INTERNAL_API_ALLOWLIST`
- `INTERNAL_API_TRUSTED_PROXIES`
- `PROMO_SECRET_PEPPER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL` password segment
- `CADDY_EMAIL`

Important:
- never use `.env.production.example` as runtime env,
- keep `.env` only on server.

Apply updated env:

```bash
cd /opt/quiz-arena
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env up -d --build
```

## 4) First-launch verification

```bash
cd /opt/quiz-arena
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env ps
bash scripts/check_compose_runtime_consistency.sh --expected-compose-file /opt/quiz-arena/docker-compose.prod.yml
curl -sS https://deutchquizarena.de/api/health
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env run --rm api python -m scripts.post_deploy_gate
```

Expected:
- all services `Up`,
- health: `status=ok`, `database=ok`, `redis=ok`, `celery=ok`,
- post-deploy gate: `all checks passed`.

## 5) Webhook setup

```bash
cd /opt/quiz-arena
source /opt/quiz-arena/.env
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=https://deutchquizarena.de/webhook/telegram" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"

curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

Expected:
- URL is `https://deutchquizarena.de/webhook/telegram`,
- `pending_update_count` не росте; якщо є `last_error_message`, тоді `last_error_date` має бути до останнього деплою.

## 6) Backup baseline (minimum)

Create initial dump before first risky changes:

```bash
cd /opt/quiz-arena
source /opt/quiz-arena/.env
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env \
  exec -T postgres sh -c 'pg_dump -U $POSTGRES_USER $POSTGRES_DB' \
  > /opt/quiz-arena/backup_first_deploy_$(date +%Y%m%d_%H%M%S).sql
```

## 7) Emergency rollback

### 7.1 Runtime rollback (code/runtime issue)

```bash
cd /opt/quiz-arena
git fetch origin
git checkout <LAST_KNOWN_GOOD_SHA_OR_TAG>
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env up -d --build
```

### 7.2 Data rollback (migration/data issue)

```bash
cd /opt/quiz-arena
source /opt/quiz-arena/.env
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env \
  exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1"

docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env \
  exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB' \
  < /opt/quiz-arena/<backup_file>.sql
```

After rollback:

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env ps
curl -sS https://deutchquizarena.de/api/health
```

## 8) Operational references

- Routine deploy: `docs/runbooks/github_to_prod_safe_deploy.md`
- Daily state checks: `docs/operations/production_state_checks.md`
