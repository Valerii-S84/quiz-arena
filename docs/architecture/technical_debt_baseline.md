# Technical Debt Baseline

Date: 2026-05-11

Scope: backend repository only. Frontend source, frontend CI, and frontend image
publishing are owned by the standalone `quiz-arena-frontend` repository.

## Current Counts

| Metric | Count |
|---|---:|
| `app/` Python files over 200 lines | 35 |
| `app/` Python files over 220 lines | 16 |
| `app/` Python files over 250 lines | 10 |
| `app/` Python files over 280 lines | 1 |
| Production functions/methods over 60 lines | 104 |
| Functions/methods with more than 7 parameters | 74 |
| Functions/methods with nesting deeper than 3 | 16 |
| Test files over 400 lines | 1 |

## Progress Since 2026-05-10 Baseline

| Metric | 2026-05-10 | 2026-05-11 | Delta |
|---|---:|---:|---:|
| `app/` Python files over 200 lines | 39 | 35 | -4 |
| `app/` Python files over 220 lines | 18 | 16 | -2 |
| `app/` Python files over 250 lines | 12 | 10 | -2 |
| `app/` Python files over 280 lines | 3 | 1 | -2 |
| Production functions/methods over 60 lines | 108 | 104 | -4 |
| Functions/methods with more than 7 parameters | 76 | 74 | -2 |
| Functions/methods with nesting deeper than 3 | 19 | 16 | -3 |
| Test files over 400 lines | 1 | 1 | 0 |

Recent refactors removed these previous top hotspots from the current top list:

- `app/bot/handlers/gameplay_duels.py`: `298` lines to `173` lines.
- `app/game/sessions/service/friend_challenges_manage.py`: `286` lines to `137`
  lines.
- `app/workers/tasks/friend_challenges_async.py::run_friend_challenge_deadlines_async`:
  no longer reports as a function over `60` lines or nesting deeper than `3`.

## Current Hotspots

Ranked by remaining size, function length, parameter count, nesting depth, and
runtime risk.

| Rank | File or function | Signal |
|---:|---|---|
| 1 | `app/db/repo/analytics_mutations.py` | `287` lines; largest remaining `app/` file. |
| 2 | `app/bot/handlers/gameplay_views_friend.py` | `276` lines; bot handler/view surface. |
| 3 | `app/game/questions/runtime_bank_mode_select.py` | `270` lines; question selection runtime path. |
| 4 | `app/bot/handlers/payments.py` | `264` lines; `handle_buy` is `116` lines. |
| 5 | `app/workers/tasks/tournaments_proof_cards_delivery.py` | `264` lines; `deliver_proof_cards` is `136` lines with `13` parameters. |
| 6 | `app/bot/handlers/start_friend_challenge_flow.py::handle_start_friend_challenge_payload` | `167` lines, `12` parameters. |
| 7 | `app/economy/promo/service.py::PromoService.redeem` | `152` lines in economy/promo write path. |
| 8 | `app/game/sessions/service/sessions_submit_friend_challenge.py::_apply_friend_challenge_answer` | `146` lines, nesting `5`. |
| 9 | `app/game/sessions/service/friend_challenges_rounds.py::start_friend_challenge_round` | `143` lines; file is `221` lines. |
| 10 | `app/bot/handlers/gameplay_flows/play_flow.py::continue_regular_mode_after_answer` | `110` lines, `10` parameters, nesting `5`. |
| 11 | `tests/game/test_sessions_start_arena.py` | `403` lines; only test file over `400`. |

## Current Files Over 220 Lines

| File | Lines |
|---|---:|
| `app/db/repo/analytics_mutations.py` | 287 |
| `app/bot/handlers/gameplay_views_friend.py` | 276 |
| `app/game/questions/runtime_bank_mode_select.py` | 270 |
| `app/bot/handlers/payments.py` | 264 |
| `app/workers/tasks/tournaments_proof_cards_delivery.py` | 264 |
| `app/bot/handlers/gameplay_flows/play_flow.py` | 257 |
| `app/economy/energy/energy_consume.py` | 257 |
| `app/game/sessions/service/sessions_submit_daily.py` | 253 |
| `app/game/sessions/service/daily_question_sets.py` | 251 |
| `app/workers/tasks/arena_duels.py` | 251 |
| `app/game/sessions/service/sessions_submit_friend_challenge.py` | 248 |
| `app/api/routes/admin/promo_models.py` | 238 |
| `app/services/analytics_daily.py` | 233 |
| `app/bot/handlers/gameplay_flows/friend_lobby_flow.py` | 226 |
| `app/bot/texts/de.py` | 223 |
| `app/game/sessions/service/friend_challenges_rounds.py` | 221 |

## Architecture Guard Status

Commands run on 2026-05-11:

| Command | Result |
|---|---|
| `bash scripts/check_line_limits.sh` | Passed with legacy warnings. |
| `.venv/bin/python scripts/check_architecture_debt.py` | Passed with legacy warnings. |
| `bash scripts/check_architecture_imports.sh` | Passed. |
| `bash scripts/check_import_cycles.sh` | Passed. |

## Guard Policy

Legacy debt is allowed only as a warning. New or worsened debt relative to
`origin/main` must fail the architecture guard.

The active guard checks:

- large files in `app/`, `tests/`, and `tools/`;
- oversized bot handler modules;
- production `app/` `def`, `async def`, and class methods;
- production `app/` functions/methods over 60 lines;
- production `app/` functions/methods with more than 7 parameters;
- production `app/` functions/methods with nesting deeper than 3;
- newly introduced or worsened debt in changed files relative to the baseline ref.

Existing guard coverage:

- `check_line_limits.sh` blocks changed files over hard file-size limits and warns
  on all `app/` files over 200 lines.
- `check_growth_delta.sh` blocks fast-growing changed `app/` files.
- `check_architecture_imports.sh` blocks domain modules importing `app.bot`.
- `check_import_cycles.sh` blocks import cycles in `app/`.
- `check_no_print_app.sh` blocks `print()` in `app/`.
- `check_no_except_exception_pass.sh` blocks `except Exception: pass`.
- `check_architecture_debt.py` blocks new or worsened structural debt and reports
  legacy structural debt as warnings.

## Legacy Allowance

The counts above are the allowed legacy baseline for this repository. They are not
an exemption for new work. Any touched file should avoid increasing these metrics,
and remediation PRs should reduce one bounded area at a time.
