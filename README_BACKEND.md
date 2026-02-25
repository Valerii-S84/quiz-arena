# Quiz Arena Backend Bootstrap

## 1. Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.lock
.venv/bin/pip install --no-deps -e .
```

Lockfiles are source-of-truth for CI/prod reproducibility:

```bash
make lock
make lock-check
```

## 2. Start infrastructure

```bash
docker compose up -d
```

Local infra expected credentials (default `docker-compose.yml`):
- Postgres user/password: `quiz` / `quiz`
- Databases:
  - app: `quiz_arena`
  - tests: `quiz_arena_test` (create via `scripts.ensure_test_db`)

If an old local Postgres volume has different credentials, recreate local containers/volumes instead of manual `ALTER USER`.

## 3. Run API

```bash
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m scripts.quizbank_import_tool --replace-all
.venv/bin/python -m app.main
```

## 4. Run bot in polling mode (dev)

```bash
.venv/bin/python scripts/run_bot_polling.py
```

## 5. Run worker

```bash
.venv/bin/python -m celery -A app.workers.celery_app worker -Q q_high,q_normal,q_low --loglevel=INFO
```

Retention cleanup defaults:
- `processed_updates`: 14 days
- `outbox_events`: 30 days
- `analytics_events`: 90 days
- Scheduled task: `app.workers.tasks.retention_cleanup.run_retention_cleanup` (hourly, queue `q_low`)

Tuning env vars:
- `QUIZ_QUESTION_POOL_CACHE_TTL_SECONDS`
- `RETENTION_PROCESSED_UPDATES_DAYS`
- `RETENTION_OUTBOX_EVENTS_DAYS`
- `RETENTION_ANALYTICS_EVENTS_DAYS`
- `RETENTION_CLEANUP_BATCH_SIZE`
- `RETENTION_CLEANUP_MAX_BATCHES_PER_TABLE`
- `RETENTION_CLEANUP_MAX_RUNTIME_SECONDS`
- `RETENTION_CLEANUP_BATCH_SLEEP_MIN_MS`
- `RETENTION_CLEANUP_BATCH_SLEEP_MAX_MS`
- `RETENTION_CLEANUP_SCHEDULE_SECONDS`
- `RETENTION_CLEANUP_SCHEDULE_HOUR_BERLIN`
- `RETENTION_CLEANUP_SCHEDULE_MINUTE_BERLIN`

## 6. Run tests

```bash
DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test \
TMPDIR=/tmp .venv/bin/python -m pytest -q -s
```

Important:
- Integration tests execute destructive `TRUNCATE` in test fixtures.
- Use only an isolated local test database whose name contains `test` (for example `quiz_arena_test`).

Recommended safe flow:
```bash
DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test \
.venv/bin/python -m scripts.ensure_test_db
DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test \
.venv/bin/python -m alembic upgrade head
DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test \
TMPDIR=/tmp .venv/bin/python -m pytest -q -s tests/integration
```

Or via Makefile:
```bash
make test
make test-integration
```

## 7. Architecture guard (pre-commit)

Install and enable pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
pre-commit run -a
```

Limits enforced (CI + pre-commit):
- `app/**/*.py` max 250 lines
- `tests/**/*.py` max 400 lines
- `tools/**/*.py` max 300 lines

Soft thresholds:
- `app/**/*.py` >200 lines → warning
- `app/**/*.py` >220 lines → CI fail unless PR contains `[APPROVED_SIZE_EXCEPTION]`

Additional guards (CI + pre-commit unless noted):
- `print(` is forbidden in `app/`
- `except Exception: pass` is forbidden anywhere in the repo
- `domains -> app.bot` imports are forbidden
- New files in `app/bot/handlers/` >180 lines → fail
- Growth delta guard (CI only): if a PR adds >50 lines to a file in `app/` and the file ends up >180 lines → fail
- Monolith warning (CI): file >=180 lines, >5 top-level `def`, >5 top-level `if` → warning

## 8. Production skeleton

- Compose stack: `docker-compose.prod.yml`
- Production env template: `.env.production.example`
- Reverse proxy config: `deploy/Caddyfile`
- Deploy helper: `scripts/deploy.sh`
- Runbook: `docs/runbooks/first_deploy_and_rollback.md`
- Post-deploy gate: `python -m scripts.post_deploy_gate` (checks `Code + Runtime + Data = head`)

## 9. QuizBank report refresh flow

Refresh all factual QuizBank reports:

```bash
make refresh-quizbank-reports
```

Verify reports are fresh (used by CI):

```bash
make check-quizbank-reports
```
