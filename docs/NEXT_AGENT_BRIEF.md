# NEXT_AGENT_BRIEF

## Current State
- M2 completed: full section-6 schema + migrations + base repositories.
- M3 completed: energy engine domain + service + tests.
- M4 completed: streak engine domain + service + tests.
- M5 phase 1 completed: `/start` onboarding integrated with DB, energy, and streak sync.
- Technical spec source of truth: `TECHNICAL_SPEC_ENERGY_STARS_BOT.md`.

## Critical Notes
- `.env` is local-only and must never be committed.
- Bot token is already configured locally; rotate token before production webhook go-live.
- Docker is currently unavailable in this WSL runtime until Docker Desktop WSL integration is enabled.
- Postgres integration/load checks are still pending in this runtime.

## Immediate Next Steps (Priority)
1. Continue Milestone 5: implement free gameplay handlers (`play`, answer flow, locked checks, daily challenge zero-cost path).
2. Implement webhook handlers and Telegram Stars payment skeleton (Milestone 6).
3. Add DB integration tests for transactional paths (onboarding, energy consume, streak activity).
4. Run migration and transaction rehearsal on staging-like Postgres runtime.

## Validation Commands
- `TMPDIR=/tmp .venv/bin/python -m pytest -q -s`
- `.venv/bin/ruff check app tests alembic scripts`
- `TMPDIR=/tmp .venv/bin/alembic heads`
