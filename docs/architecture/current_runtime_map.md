# Current Runtime Map

Operational architecture map for current production/runtime behavior.

Last verified: 2026-07-18 against `docker-compose.prod.yml`,
`deploy/Caddyfile`, `app/main.py`, and `app/bot/application.py`.

## 1) Runtime Topology

```text
Browser / Telegram
        |
        v
 Caddy (TLS, reverse proxy)
        |
        +--> frontend:3000 (website/admin UI and quiz teaser routes)
        |
        +--> api:8000 (FastAPI API, health, and Telegram webhook)
                  |
                  +--> PostgreSQL (domain + ops data)
                  +--> Redis (Celery broker/result and runtime state)
                              |
                              v
                    Celery worker(s) + Celery beat
```

Main deploy stack is defined in `docker-compose.prod.yml`:
- `caddy`
- `frontend` (prebuilt image supplied by `FRONTEND_IMAGE`)
- `api`
- `worker`
- `beat`
- `postgres`
- `redis`

Caddy also reaches the separately managed QuizBank API container through the
external `api_quiz_bank` Docker network; that container is not defined by this
repository's production compose file.

## 2) Inbound Telegram Flow (Webhook -> Queue -> Worker)

### 2.1 Webhook ingress

Route: `POST /webhook/telegram` (`app/api/routes/telegram_webhook.py`)

Flow:
1. Validate `X-Telegram-Bot-Api-Secret-Token` against `TELEGRAM_WEBHOOK_SECRET`.
2. Parse JSON payload and extract `update_id`.
3. Enqueue `process_telegram_update` Celery task with timeout
   (`TELEGRAM_WEBHOOK_ENQUEUE_TIMEOUT_MS`).
4. If enqueue fails or times out -> return `503 {"status":"retry"}`.
5. If enqueue succeeds -> return `200 {"status":"queued"}`.

Runtime invariant:
- Webhook never acknowledges (`2xx`) an update that was not queued.

### 2.2 Worker processing and idempotency

Task: `app.workers.tasks.telegram_updates.process_telegram_update`

Flow:
1. Acquire processing slot in `processed_updates` by `update_id`.
   - New row -> `PROCESSING`.
   - Duplicate already processed -> skip.
   - Reclaim stale/failed slot -> continue.
2. Validate payload as aiogram `Update`.
3. Dispatch through bot dispatcher (`app.bot.application` routers).
4. On success -> mark `processed_updates.status=PROCESSED`.
5. On unexpected error -> mark status `FAILED`, retry via Celery backoff+jitter
   (`TELEGRAM_UPDATE_TASK_MAX_RETRIES`, `TELEGRAM_UPDATE_TASK_RETRY_BACKOFF_MAX_SECONDS`).
6. On non-retryable Telegram API errors (`TelegramBadRequest`, `TelegramForbiddenError`) ->
   mark as `PROCESSED` to avoid retry spam.

Reliability events are written to `outbox_events`:
- `telegram_update_reclaimed`
- `telegram_update_retry_scheduled`
- `telegram_update_failed_final`

Delivery model:
- At-least-once delivery from Telegram/Celery.
- Exactly-once effect for update processing is approximated by `processed_updates` idempotency.

## 3) Bot Orchestration Layer

Dispatcher routers (`app.bot.application`):
- `start`
- `channel_bonus`
- `gameplay_inline_share`
- `gameplay`
- `offers`
- `payments`
- `promo`
- `referral`

Architecture rule:
- Bot handlers orchestrate; business logic lives in domain/services modules.

## 4) Scheduled/Async Processing

`beat` schedules periodic tasks; `worker` executes them.

Task groups active in current runtime include:
- telegram update reliability/observability
- payments reliability/reconciliation
- offers/referrals observability
- promo maintenance
- daily challenge
- friend challenges
- tournaments + tournament messaging/proof cards
- daily cup
- retention cleanup
- analytics daily aggregation

These tasks read/write domain tables and can emit:
- `outbox_events` (ops/reliability events)
- `analytics_events` (product/ops analytics events)
- `analytics_daily` (aggregated KPIs)

## 5) HTTP Surfaces

Mounted in `app.main`:
- Health/readiness:
  - `GET /live`
  - `GET /ready`
  - `GET /health`
- Internal dashboards/APIs:
  - `/internal/promo/*`
  - `/internal/offers/*`
  - `/internal/referrals/*`
  - `/internal/analytics/*`
- Ops UI:
  - `/ops/*`
  - static assets at `/ops/static`
- Admin API:
  - `/admin/auth/*`
  - `/admin/overview`
  - `/admin/users/*`, `/admin/economy/*`, `/admin/promo/*`
  - `/admin/content/*`, `/admin/system`, `/admin/contact-requests/*`
  - `/admin/website-analytics/overview`
- Public API used by the frontend:
  - `/api/contact`, `/api/stats`
  - `/api/public/website-analytics/events`
  - compatibility routes without the `/api` prefix remain mounted in FastAPI

Internal/ops access protection:
- IP allowlist (`INTERNAL_API_ALLOWLIST`)
- trusted proxy parsing (`INTERNAL_API_TRUSTED_PROXIES`)
- token auth via `X-Internal-Token` / ops session cookie

Admin APIs use the dedicated admin authentication/session flow under
`app/api/routes/admin/`.

## 6) Core Data Surfaces (PostgreSQL)

High-impact runtime tables:
- Telegram processing: `processed_updates`
- Operations/reliability events: `outbox_events`
- Product analytics events: `analytics_events`, `analytics_daily`
- Users/gameplay: `users`, `quiz_sessions`, `quiz_attempts`, `quiz_questions`
- Economy/payments: `energy_state`, `ledger_entries`, `entitlements`, `purchases`,
  `telegram_update_inbox`, `payment_events`, `payment_reconciliation_reviews`
- Promo/referrals: `promo_*`, `referrals`
- Competitive modes: `friend_challenges`, `arena_duels`, `arena_attempts`,
  `tournaments`, `tournament_participants`, `tournament_matches`,
  `tournament_round_scores`
- Admin/public site: `admins`, `admin_audit_log`, `contact_requests`,
  `website_events`
- Delivery reliability: `telegram_delivery_attempts`

## 7) Critical Runtime Config

Webhook/reliability:
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_WEBHOOK_ENQUEUE_TIMEOUT_MS`
- `TELEGRAM_UPDATE_PROCESSING_TTL_SECONDS`
- `TELEGRAM_UPDATE_TASK_MAX_RETRIES`
- `TELEGRAM_UPDATE_TASK_RETRY_BACKOFF_MAX_SECONDS`

Infra:
- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `FRONTEND_IMAGE`
- `FRONTEND_API_INTERNAL_URL`
- `QUIZ_BANK_API_BASE_URL`
- `QUIZ_BANK_EDGE_API_KEY`
- `QUIZ_BANK_CONSUMER_ID`
- `QUIZ_BANK_CONSUMER_API_KEY`

Ops security:
- `INTERNAL_API_TOKEN`
- `INTERNAL_API_ALLOWLIST`
- `INTERNAL_API_TRUSTED_PROXIES`

## 8) Related Docs

- Deploy flow: `docs/runbooks/github_to_prod_safe_deploy.md`
- First deploy/rollback: `docs/runbooks/first_deploy_and_rollback.md`
- Daily production checks: `docs/operations/production_state_checks.md`
