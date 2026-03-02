# Quiz Arena Backend Bootstrap

Canonical repository entrypoint is `README.md`.
This file stays as backend-oriented quick reference.

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

## 2. Start local infrastructure

```bash
docker compose up -d
```

Optional full-stack mode (API + frontend dashboard):

```bash
docker compose --profile frontend up -d
```

Default local credentials (`docker-compose.yml`):
- Postgres user/password: `quiz` / `quiz`
- Databases:
  - app: `quiz_arena`
  - tests: `quiz_arena_test`

If an old local Postgres volume has different credentials, recreate local containers/volumes instead of manual `ALTER USER`.

## 3. Run app stack locally

```bash
# DB schema + content
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m scripts.quizbank_import_tool --replace-all

# API
.venv/bin/python -m app.main

# Worker
.venv/bin/python -m celery -A app.workers.celery_app worker -Q q_high,q_normal,q_low --loglevel=INFO

# Beat
.venv/bin/python -m celery -A app.workers.celery_app beat --loglevel=INFO

# Optional Telegram polling mode for dev
.venv/bin/python scripts/run_bot_polling.py
```

Retention cleanup defaults:
- `processed_updates`: 14 days
- `outbox_events`: 30 days
- `analytics_events`: 90 days
- Scheduled task: `app.workers.tasks.retention_cleanup.run_retention_cleanup` (hourly, queue `q_low`)

## 4. Mandatory quality gate

```bash
.venv/bin/ruff check .
.venv/bin/mypy .
DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test TMPDIR=/tmp .venv/bin/pytest -q
```

Safe integration-only flow:

```bash
DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test .venv/bin/python -m scripts.ensure_test_db
DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test .venv/bin/python -m alembic upgrade head
DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test TMPDIR=/tmp .venv/bin/pytest -q tests/integration
```

## 5. Architecture and CI guards

- `print(` is forbidden in `app/`
- `except Exception: pass` is forbidden in repo
- `domains -> app.bot` imports are forbidden
- New files in `app/bot/handlers/` over 180 lines fail CI
- Growth delta guard and monolith warning are enabled in CI

Full rules:
- `CODE_STYLE.md`
- `ENGINEERING_RULES.md`
- `REPO_STRUCTURE.md`

## 6. Production references

- Runtime stack: `docker-compose.prod.yml`
- Production env template: `.env.production.example`
- Reverse proxy config: `deploy/Caddyfile`
- Deploy helper: `scripts/deploy.sh`
- Main deploy runbook: `docs/runbooks/github_to_prod_safe_deploy.md`
- First deploy/rollback baseline: `docs/runbooks/first_deploy_and_rollback.md`
- Post-deploy gate command:
  - `docker compose -f docker-compose.prod.yml run --rm api python -m scripts.post_deploy_gate`

## 7. QuizBank reports

Refresh reports:

```bash
make refresh-quizbank-reports
```

Verify freshness (CI uses this):

```bash
make check-quizbank-reports
```
