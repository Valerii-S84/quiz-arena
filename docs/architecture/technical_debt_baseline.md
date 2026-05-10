# Technical Debt Baseline

Date: 2026-05-10

Scope: backend repository only. Frontend source, frontend CI, and frontend image
publishing are owned by the standalone `quiz-arena-frontend` repository.

## Current Counts

| Metric | Count |
|---|---:|
| `app/` Python files over 200 lines | 39 |
| `app/` Python files over 220 lines | 18 |
| `app/` Python files over 250 lines | 12 |
| `app/` Python files over 280 lines | 3 |
| Production functions/methods over 60 lines | 108 |
| Functions/methods with more than 7 parameters | 76 |
| Functions/methods with nesting deeper than 3 | 19 |
| Test files over 400 lines | 1 |

## Hotspots

| File or function | Signal |
|---|---|
| `app/bot/handlers/gameplay_duels.py` | 298 lines, 61.21% coverage |
| `app/db/repo/analytics_mutations.py` | 287 lines, 62.90% coverage |
| `app/game/sessions/service/friend_challenges_manage.py` | 286 lines, 89.40% coverage |
| `app/bot/handlers/gameplay_flows/answer_flow.py::handle_answer` | 189 lines, 26 parameters |
| `app/workers/tasks/friend_challenges_async.py::run_friend_challenge_deadlines_async` | 171 lines, nesting 5 |
| `app/bot/handlers/gameplay_flows/friend_answer_flow.py::handle_friend_answer_branch` | 169 lines, 17 parameters |
| `tests/game/test_sessions_start_arena.py` | 404 lines |

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
