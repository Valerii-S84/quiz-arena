# Quiz Arena

Production-grade Telegram quiz bot for German learning.

## Stack

- API: FastAPI (`app.main`)
- Bot: aiogram webhook + optional local polling
- Background jobs: Celery worker + beat
- Data: PostgreSQL + Redis
- Runtime: Docker Compose + Caddy (HTTPS reverse proxy)

## Quick Start (Local)

1. Install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.lock
.venv/bin/pip install --no-deps -e .
```

2. Start local infra:

```bash
docker compose up -d
```

3. Prepare database + content:

```bash
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m scripts.quizbank_import_tool --replace-all
```

4. Run services:

```bash
# API
.venv/bin/python -m app.main

# Worker
.venv/bin/python -m celery -A app.workers.celery_app worker -Q q_high,q_normal,q_low --loglevel=INFO

# Beat
.venv/bin/python -m celery -A app.workers.celery_app beat --loglevel=INFO

# Optional bot polling (dev only)
.venv/bin/python scripts/run_bot_polling.py
```

## Mandatory Local Gate

Use only the project venv binaries:

```bash
.venv/bin/ruff check .
.venv/bin/mypy .
DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test TMPDIR=/tmp .venv/bin/pytest -q
```

## Production Deploy

- Primary runbook: `docs/runbooks/github_to_prod_safe_deploy.md`
- First deploy / rollback baseline: `docs/runbooks/first_deploy_and_rollback.md`
- Deploy helper: `scripts/deploy.sh`
- Runtime stack: `docker-compose.prod.yml`

## Documentation Map

Core engineering rules:
- `AGENTS.md`
- `CODE_STYLE.md`
- `ENGINEERING_RULES.md`
- `REPO_STRUCTURE.md`

Operational docs:
- `docs/runbooks/`
- `docs/architecture/`
- `docs/database/`
- `docs/analytics/`
- `docs/performance/`
- `docs/metrics/`
- `docs/operations/`

Product/domain docs:
- `PRODUCT/`
- `QuizBank/README.md`

Reports and one-off artifacts:
- `reports/`
- `docs/archive/`

## Documentation Hygiene

- Canonical entrypoint is this file (`README.md`).
- `README_BACKEND.md` is kept for compatibility and backend-focused bootstrap details.
- Historical planning/handoff documents should be treated as archive material, not source-of-truth for current runtime behavior.
