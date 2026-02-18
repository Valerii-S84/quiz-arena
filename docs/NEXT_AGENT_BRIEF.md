# NEXT_AGENT_BRIEF

## Current State
- Milestone 2 completed: full section-6 schema + migrations + base repositories.
- Milestone 3 completed (domain level): energy engine rules + service + tests.
- Milestone 4 completed (domain level): streak engine rules + service + tests.
- Technical spec source of truth: `TECHNICAL_SPEC_ENERGY_STARS_BOT.md`.

## Critical Notes
- `.env` is local-only and must never be committed.
- Bot token is already configured locally; rotate token before production webhook go-live.
- Docker is currently unavailable in this WSL runtime until Docker Desktop WSL integration is enabled.
- Postgres integration/load checks are still pending in this runtime.

## Immediate Next Steps (Priority)
1. Implement Milestone 5: Free Tier gameplay handlers integrated with M3/M4 services.
2. Implement webhook handlers and Telegram Stars payment flow skeleton (Milestone 6 prep).
3. Add DB integration tests for idempotent transactional flows (energy consume, purchase credit, streak update).
4. Run migration up/down rehearsal on staging-like Postgres runtime.

## Validation Commands
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s`
- `.venv/bin/ruff check app tests alembic scripts`
- `TMPDIR=/tmp .venv/bin/alembic heads`
