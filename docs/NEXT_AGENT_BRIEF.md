# NEXT_AGENT_BRIEF

## Current State
- Backend bootstrap completed (FastAPI + aiogram + Celery + Alembic skeleton).
- Milestone 2 completed: section-6 schema models + Alembic migrations + base repositories.
- Base tests and metadata checks are green.
- Technical spec source of truth: `TECHNICAL_SPEC_ENERGY_STARS_BOT.md`.

## Critical Notes
- `.env` is local-only and must never be committed.
- Bot token is already configured locally; rotate token before production webhook go-live.
- Docker is currently unavailable in this WSL runtime until Docker Desktop WSL integration is enabled.
- Postgres migration `upgrade/downgrade` rehearsal was not run locally due missing DB runtime.

## Immediate Next Steps (Priority)
1. Implement Milestone 3: Energy engine (transaction-safe consume/regen/top-up).
2. Implement Milestone 4: Streak engine with Berlin timezone and DST-safe day logic.
3. Implement webhook handlers and payment flow stubs for Telegram Stars.
4. Add DB integration tests for migration up/down and core transactional paths.

## Validation Commands
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s`
- `.venv/bin/ruff check app tests alembic scripts`
- `TMPDIR=/tmp .venv/bin/alembic heads`
