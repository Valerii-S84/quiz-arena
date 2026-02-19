# Next Agent Handoff (2026-02-19)

## Update (2026-02-19, promo dashboard)
- Delivered dedicated promo observability endpoint:
  - `GET /internal/promo/dashboard`
  - internal auth parity with redeem endpoint (`X-Internal-Token` + IP allowlist).
- Dashboard output now includes:
  - promo conversion metrics (`attempts accepted/failed`, `discount reservation->applied`);
  - failure-rate breakdown by attempt result (`INVALID`, `EXPIRED`, `NOT_APPLICABLE`, `RATE_LIMITED`);
  - guard trigger indicators (`candidate abusive hashes`, `paused campaign totals/recent`).
- Added/updated tests:
  - `tests/api/test_internal_promo_auth.py` (dashboard auth coverage),
  - `tests/integration/test_internal_promo_dashboard_integration.py` (metrics correctness).
- Milestone ops note updated:
  - `docs/milestones/M10_ops.md` now records the dashboard endpoint as implemented.

## What was completed
- Friend challenge flow implemented and stabilized:
  - 12-round plan with fixed level sequence `A1x3 + A2x6 + B1x3`.
  - Both players receive the same question per round.
  - Opponent labels resolve to username/first name instead of generic `Freund`.
  - Creator can continue all rounds without waiting; round/final score updates are synced.
  - Free quota and paid ticket/premium rules wired for friend challenges.
- Friend challenge invite UX updated:
  - Share-first flow with Telegram native share URL (`Link teilen`).
  - Separate action to start duel after link sharing.
- Promo handling fixed:
  - Promo is no longer auto-captured from unrelated text by default.
  - Promo redemption runs only from explicit promo entry points.
  - Internal promo integration tests pass.
- `ARTIKEL_SPRINT` adaptive progression fixed:
  - New users start at `A1`.
  - Progress now persists across sessions/days in new table `mode_progress`.
  - Existing users without a progress row are backfilled from most recent `ARTIKEL_SPRINT` history.
  - Bounds clamped to mode range (`A1..B2`) to avoid invalid upward jumps.

## New DB migration
- Added migration:
  - `alembic/versions/d5e6f7a8b9c0_m14_add_mode_progress_table.py`
- Current DB head verified: `d5e6f7a8b9c0`.
- Promo dashboard delivery in this update did not require DB migrations.

## Important operational notes
- Integration tests truncate core tables including:
  - `quiz_questions`
  - `promo_codes` and related promo tables
- If tests are run on shared/dev DB, re-seed after tests:
  - Re-import quiz bank.
  - Recreate required promo codes (e.g. `CHIK`) if needed.

## Validation performed
- `pytest -q -s tests/game/test_adaptive_difficulty.py tests/integration/test_artikel_sprint_progress_integration.py tests/test_data_model_metadata.py` -> passed.
- `pytest -q -s tests/integration/test_friend_challenge_integration.py::test_friend_challenge_default_uses_12_round_plan_with_level_mix_and_free_energy` -> passed.
- `ruff` checks for touched files -> passed.
- `pytest -q -s tests/api/test_internal_promo_auth.py tests/integration/test_internal_promo_dashboard_integration.py` -> passed.
- `ruff check app/api/routes/internal_promo.py app/db/repo/promo_repo.py tests/api/test_internal_promo_auth.py tests/integration/test_internal_promo_dashboard_integration.py` -> passed.

## Runtime state at handoff
- Background API and worker processes were explicitly stopped before handoff.
- Workspace prepared for clean startup by next agent.
