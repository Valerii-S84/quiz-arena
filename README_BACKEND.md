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
TMPDIR=/tmp .venv/bin/python -m pytest -q -s
```

## 7. Production skeleton

- Compose stack: `docker-compose.prod.yml`
- Production env template: `.env.production.example`
- Reverse proxy config: `deploy/Caddyfile`
- Deploy helper: `scripts/deploy.sh`
- Runbook: `docs/runbooks/first_deploy_and_rollback.md`
