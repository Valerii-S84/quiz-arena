# Quiz Arena Backend Bootstrap

## 1. Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
```

## 2. Start infrastructure

```bash
docker compose up -d
```

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

## 7. Production skeleton

- Compose stack: `docker-compose.prod.yml`
- Production env template: `.env.production.example`
- Reverse proxy config: `deploy/Caddyfile`
- Deploy helper: `scripts/deploy.sh`
- Runbook: `docs/runbooks/first_deploy_and_rollback.md`
