# Production Env Ownership Matrix

Status: draft plan only. Key names only; no secret values.

## Source Inventories

Current live inventory confirmed these active env sources:

- `/opt/quiz-arena/.env`
- `/opt/api-quiz-bank/.env`

Target env files:

- `.env.quiz-arena`
- `.env.site`
- `.env.quiz-bank`
- `.env.caddy`

## `.env.quiz-arena`

Keys currently in `/opt/quiz-arena/.env` that should remain with the Quiz Arena
backend/runtime:

- `ADMIN_2FA_REQUIRED`
- `ADMIN_ACCESS_TOKEN_TTL_MINUTES`
- `ADMIN_EMAIL`
- `ADMIN_FRONTEND_ORIGIN`
- `ADMIN_JWT_SECRET`
- `ADMIN_LOGIN_RATE_LIMIT_ATTEMPTS`
- `ADMIN_LOGIN_RATE_LIMIT_WINDOW_MINUTES`
- `ADMIN_PASSWORD_HASH`
- `ADMIN_PASSWORD_PLAIN`
- `ADMIN_REFRESH_SECRET`
- `ADMIN_REFRESH_TOKEN_TTL_DAYS`
- `ADMIN_TOTP_ISSUER`
- `ADMIN_TOTP_SECRET`
- `API_WORKERS`
- `APP_ENV`
- `APP_HOST`
- `APP_PORT`
- `BONUS_CHANNEL_ID`
- `BONUS_CHECK_BOT_TOKEN`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `CELERY_WORKER_CONCURRENCY`
- `DATABASE_URL`
- `ENABLE_OPENAPI_DOCS`
- `FRIEND_CHALLENGE_DEADLINE_BATCH_SIZE`
- `FRIEND_CHALLENGE_DEADLINE_SCAN_INTERVAL_SECONDS`
- `FRIEND_CHALLENGE_LAST_CHANCE_SECONDS`
- `FRIEND_CHALLENGE_TTL_SECONDS`
- `INTERNAL_API_ALLOWLIST`
- `INTERNAL_API_TOKEN`
- `INTERNAL_API_TRUSTED_PROXIES`
- `LOG_LEVEL`
- `OFFERS_ALERT_MAX_DISMISS_RATE`
- `OFFERS_ALERT_MAX_IMPRESSIONS_PER_USER`
- `OFFERS_ALERT_MIN_CONVERSION_RATE`
- `OFFERS_ALERT_MIN_IMPRESSIONS`
- `OFFERS_ALERT_WINDOW_HOURS`
- `OPS_ALERT_ESCALATION_POLICY_JSON`
- `OPS_ALERT_PAGERDUTY_EVENTS_URL`
- `OPS_ALERT_PAGERDUTY_ROUTING_KEY`
- `OPS_ALERT_SLACK_WEBHOOK_URL`
- `OPS_ALERT_WEBHOOK_URL`
- `POSTGRES_DB`
- `POSTGRES_PASSWORD`
- `POSTGRES_USER`
- `PROMO_ENCRYPTION_KEY`
- `PROMO_SECRET_PEPPER`
- `PYTHONDONTWRITEBYTECODE`
- `PYTHONUNBUFFERED`
- `QUIZ_QUESTION_POOL_CACHE_TTL_SECONDS`
- `REDIS_URL`
- `REFERRALS_ALERT_MAX_FRAUD_REJECTED_RATE`
- `REFERRALS_ALERT_MAX_REFERRER_REJECTED_FRAUD`
- `REFERRALS_ALERT_MAX_REJECTED_FRAUD_TOTAL`
- `REFERRALS_ALERT_MIN_STARTED`
- `REFERRALS_ALERT_WINDOW_HOURS`
- `RETENTION_ANALYTICS_EVENTS_DAYS`
- `RETENTION_CLEANUP_BATCH_SIZE`
- `RETENTION_CLEANUP_BATCH_SLEEP_MAX_MS`
- `RETENTION_CLEANUP_BATCH_SLEEP_MIN_MS`
- `RETENTION_CLEANUP_MAX_BATCHES_PER_TABLE`
- `RETENTION_CLEANUP_MAX_RUNTIME_SECONDS`
- `RETENTION_CLEANUP_SCHEDULE_HOUR_BERLIN`
- `RETENTION_CLEANUP_SCHEDULE_MINUTE_BERLIN`
- `RETENTION_CLEANUP_SCHEDULE_SECONDS`
- `RETENTION_OUTBOX_EVENTS_DAYS`
- `RETENTION_PROCESSED_UPDATES_DAYS`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_HOME_HEADER_FILE_ID`
- `TELEGRAM_UPDATES_ALERT_WINDOW_MINUTES`
- `TELEGRAM_UPDATES_FAILED_FINAL_SPIKE_THRESHOLD`
- `TELEGRAM_UPDATES_OBSERVABILITY_TOP_STUCK_LIMIT`
- `TELEGRAM_UPDATES_RETRY_SPIKE_THRESHOLD`
- `TELEGRAM_UPDATES_STUCK_ALERT_MIN_MINUTES`
- `TELEGRAM_UPDATE_PROCESSING_TTL_SECONDS`
- `TELEGRAM_UPDATE_TASK_MAX_RETRIES`
- `TELEGRAM_UPDATE_TASK_RETRY_BACKOFF_MAX_SECONDS`
- `TELEGRAM_WEBHOOK_ENQUEUE_TIMEOUT_MS`
- `TELEGRAM_WEBHOOK_SECRET`

## `.env.site`

Keys currently in `/opt/quiz-arena/.env` that should move to the
`quiz-arena-site` stack:

- `FRONTEND_IMAGE`
- `QUIZ_BANK_API_BASE_URL`
- `QUIZ_BANK_CONSUMER_API_KEY`
- `QUIZ_BANK_CONSUMER_ID`
- `QUIZ_BANK_EDGE_API_KEY`

Target explicit site key to add during the split if the frontend still needs
server-side access to Quiz Arena API:

- `FRONTEND_API_INTERNAL_URL`

Compose-level values that can stay hardcoded unless the site repo requires
otherwise:

- `NODE_ENV`
- `NEXT_PUBLIC_API_URL`

## `.env.caddy`

Keys currently in `/opt/quiz-arena/.env` that should move to `infra-caddy`:

- `API_QUIZ_BANK_PUBLIC_API_KEY`
- `CADDY_EMAIL`
- `DOMAIN`

## `.env.quiz-bank`

Keys currently in `/opt/api-quiz-bank/.env` that belong to API Quiz Bank:

- `API_QUIZ_BANK_POSTGRES_DB`
- `API_QUIZ_BANK_POSTGRES_PASSWORD`
- `API_QUIZ_BANK_POSTGRES_USER`
- `QUIZBANK_DB_PATH`
- `QUIZBANK_ENV`
- `QUIZBANK_HOST`
- `QUIZBANK_PORT`

Example-only API Quiz Bank keys seen in the repo template and not confirmed in
the active runtime file:

- `QUIZBANK_TELEGRAM_BOT_TOKEN_FILE`
- `TELEGRAM_BOT_TOKEN_FILE`

## Current-Only Review Keys

These keys were present in the `/opt/quiz-arena/.env` key inventory but look
like image/base-environment keys, not application ownership boundaries. Do not
move them blindly. Either prove they are needed in `.env.quiz-arena` or remove
them from managed env files during a separate approved cleanup:

- `GPG_KEY`
- `LANG`
- `PATH`
- `PYTHON_SHA256`
- `PYTHON_VERSION`

## Split Rules

- Never print values while splitting env files.
- Create target env files from a secure shell/editor session on the VPS only
  during the approved migration window.
- Keep the original `/opt/quiz-arena/.env` and `/opt/api-quiz-bank/.env`
  backups until the stability window is complete.
- Use `docker compose --env-file <target-env-file>` consistently for target
  stacks because service-level `env_file` does not provide compose
  interpolation values.
