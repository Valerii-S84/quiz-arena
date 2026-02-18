# NEXT_AGENT_BRIEF

## Current State
- M2 completed: full section-6 schema + migrations + base repositories.
- M3 completed: energy engine domain + service + tests.
- M4 completed: streak engine domain + service + tests.
- M5 completed as functional free-loop slice (start/menu/play/answer/locked/daily challenge).
- M6 slice 1 completed: Telegram micro-purchase callback flow (buy -> pre_checkout -> successful_payment -> credit apply).
- Technical spec source of truth: `TECHNICAL_SPEC_ENERGY_STARS_BOT.md`.

## Critical Notes
- `.env` is local-only and must never be committed.
- Bot token is already configured locally; rotate token before production webhook go-live.
- Docker is currently unavailable in this WSL runtime until Docker Desktop WSL integration is enabled.
- Postgres integration/load checks are still pending in this runtime.

## Immediate Next Steps (Priority)
1. Implement webhook endpoint and queued update processing (`/webhook/telegram`).
2. Add payment recovery and reconciliation jobs for `PAID_UNCREDITED` and ledger consistency.
3. Replace static question bank with real selection/anti-repeat logic.
4. Add DB integration tests for payment and callback idempotency under duplicates.

## Validation Commands
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s`
- `.venv/bin/ruff check app tests alembic scripts`
- `TMPDIR=/tmp .venv/bin/alembic heads`
