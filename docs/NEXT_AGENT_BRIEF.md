# NEXT_AGENT_BRIEF

## Current State
- Backend bootstrap completed (FastAPI + aiogram + Celery + Alembic skeleton).
- Milestone 2 completed: section-6 schema models + Alembic migrations + base repositories.
- Milestone 3 implemented at domain level: energy engine rules + service + unit tests.
- Technical spec source of truth: `TECHNICAL_SPEC_ENERGY_STARS_BOT.md`.

## Critical Notes
- `.env` is local-only and must never be committed.
- Bot token is already configured locally; rotate token before production webhook go-live.
- Docker is currently unavailable in this WSL runtime until Docker Desktop WSL integration is enabled.
- Postgres migration `upgrade/downgrade` rehearsal and M3 concurrency checks were not run locally due missing DB runtime.

## Immediate Next Steps (Priority)
1. Implement Milestone 4: Streak engine with Berlin timezone and DST-safe day logic.
2. Integrate M3 energy service into handlers/webhook flow (play start, payment credit paths).
3. Add DB integration tests for migration up/down and transactional idempotency paths.
4. Implement webhook handlers and payment flow stubs for Telegram Stars.

## Validation Commands
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s`
- `.venv/bin/ruff check app tests alembic scripts`
- `TMPDIR=/tmp .venv/bin/alembic heads`
