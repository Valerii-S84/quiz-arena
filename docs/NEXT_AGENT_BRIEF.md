# NEXT_AGENT_BRIEF

## Current State
- Backend bootstrap completed (FastAPI + aiogram + Celery + Alembic skeleton).
- Base health tests are green.
- Technical spec source of truth: `TECHNICAL_SPEC_ENERGY_STARS_BOT.md`.

## Critical Notes
- `.env` is local-only and must never be committed.
- Bot token is already configured locally; rotate token before production webhook go-live.
- Docker is currently unavailable in this WSL runtime until Docker Desktop WSL integration is enabled.

## Immediate Next Steps (Priority)
1. Implement Milestone 2: real DB models + migrations per spec section 6.
2. Implement Milestone 3: Energy engine (transaction-safe consume/regen/top-up).
3. Implement Milestone 4: Streak engine with Berlin timezone and DST-safe day logic.
4. Add webhook handlers and payment flow stubs for Telegram Stars.

## Validation Commands
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s`
- `.venv/bin/ruff check app tests alembic scripts`
