# Production critical flows hardening tracker 2026-07-10

Status: `BLOCKED_ON_LINE_LIMIT_GATE` for the PR #246 blocking fix pass. Runtime/test fixes are local only and were not pushed because the forced local line-limit gate is still red.

Safety boundary for this PR:
- no deploy;
- no production DB writes;
- no production migrations;
- no production restarts;
- no task replay;
- no manual messaging;
- no `.env*`, secrets, deploy config, or `docker-compose.prod.yml` changes;
- auto-recovery remains off;
- live reconciliation is not enabled.

## Gap matrix closure

| Blocker | Code area | Invariant added | Migration | Tests |
| --- | --- | --- | --- | --- |
| Durable Telegram delivery outcomes | `telegram_delivery_attempts`, `app/services/telegram_delivery.py`, Daily Cup/private tournament/beaten flows | every expected target is `SENT`, `FAILED`, or `SKIPPED`; duplicate runs use DB-backed idempotency | `b6c7d8e9f012_m56_production_reliability_foundation.py` | delivery repo/service/worker tests |
| Daily Cup push fake sent idempotency | `daily_cup_registration_push.py` | analytics sent event is written only after Telegram send and delivery `SENT` | yes | registration push unit tests |
| Worker/beat heartbeat | `worker_task_heartbeats`, `app/workers/task_heartbeat.py` | task start/success/failure and last-success are durable; stale checker has registry | yes | heartbeat and wrapper tests |
| Production invariant checker | `app/services/production_invariants.py`, `scripts/production_critical_invariants.py` | read-only P0/P1/P2 checks with stable JSON/text output | no | checker script/service tests |
| Durable P1/P2 alerts | `production_invariant_alerts`, `production_invariant_alerts.py` | active failures upsert/reopen OPEN alerts; OK checks resolve existing OPEN alert | yes | alert task and repo lifecycle tests |
| Premium expiry lifecycle | `premium_expiry.py`, `EntitlementsRepo` | expired ACTIVE premium can be marked `EXPIRED` idempotently; effective lookup remains time-aware | no extra table | premium expiry tests |
| Telegram blocked/failure state | delivery attempt failure classification | 403/bot blocked/chat missing becomes failed blocked candidate; future mass send can skip known blocked candidate | yes | Telegram delivery service tests |
| Messaging repair-ready path | `messaging_repair_planner.py` | dry-run plan lists expected, existing, missing, failed, skipped, safe replay candidates without sending | no | repair planner tests |
| Streak/global/analytics freshness | production invariant checker | stale streak, inconsistent global source, stale analytics, and stuck scheduled offer delivery attempts are visible | no | checker coverage tests |

## Acceptance criteria

Code-level criteria met:
- durable delivery attempt model/repo/service added;
- Daily Cup registration, reminders, round/cancel, private tournament, and beaten notification entrypoints record outcomes;
- heartbeat wrapper and critical task registry added;
- read-only invariant checker added;
- durable alert task added;
- premium expiry task added but not run in production;
- dry-run repair planner added;
- runbooks and operations docs added.

Deploy-only criteria not performed in this PR:
- apply migration on production;
- deploy worker/API/beat code;
- run production checker after migration;
- execute post-deploy smoke;
- confirm monitoring and ads readiness.

## Local evidence

Targeted checks completed during implementation:
- delivery focused suite: `31 passed`;
- heartbeat/premium focused suites: `19 passed`, `25 passed`;
- invariant/repair/alert suites: `23 passed`;
- formatting/lint focused checks passed for changed code.

## PR #246 blocking fix pass - 2026-07-10

Status: `BLOCKED_ON_LINE_LIMIT_GATE`.

### Stage 0 - CI failure triage

- GitHub check/job: PR #246 head `8769e765268d9761481eb8685a065b5570917754`, workflow `CI` run `29105331136`, job `lint_unit` / `86404290533`.
- GitHub API result: `lint_unit` failed; `integration` and `tournament_regression` were skipped because `lint_unit` failed.
- GitHub job steps: `Ruff`, `Black`, `isort`, and `Mypy` passed; step `Pytest (unit and bot)` failed.
- GitHub log limitation: unauthenticated `gh` is unavailable and direct job-log download returned `403 Must have admin rights to Repository`; public job page exposes only the pytest step failure annotation.
- Exact reproduced command: `.venv/bin/python -m pytest -q --ignore=tests/integration` with the same CI env values from `.github/workflows/ci.yml`.
- Exact reproduced failure: `9 failed, 2108 passed, 1 skipped`.
- Root cause: unit test expectations were stale after the PR introduced delivery `skipped` result fields and durable delivery preparation calls; tests either still expected the old result shape or exercised delivery code without a stubbed delivery repository/session.
- Minimal fix: update only the affected unit tests and the narrow production fixes required by Codex P1/P2/P3 findings; no CI bypass, no disabled tests, no line-limit increase.

### Codex findings fixed

- P1 Daily Cup idempotency: round messaging targets now include tournament id, user id, operation, status/current round, and content version; fallback send after failed edit has its own durable key.
- P1 private tournament idempotency: private round messaging uses the same versioned target pattern and keeps per-user outcomes independent.
- P1 controlled replay: `SENT` and `SKIPPED` remain non-retryable; unsafe fresh/stale `PENDING` sends stay blocked; stale `PENDING` retry is allowed only for explicit replay-safe edit attempts; retryable `FAILED` is limited to Telegram retry-after failures and bounded by max attempts.
- P2 Daily Cup per-participant gap: invariant checker now has `daily_cup_round_delivery_gap` over active eligible participants and excludes canceled cups from round gap alerts.
- P2 blocked candidates: current blocked state now ignores old blocked failures after TTL or newer inbound user activity via `users.last_seen_at`.
- P2 streak stale: checker now correlates recent `quiz_attempts.user_id` to the same user's `streak_state.updated_at`.
- P3 alert reopen count: `record_open` returns immediately after reopening a terminal alert row.

### Local gate evidence after fix pass

- Focused blocker suite: `.venv/bin/python -m pytest -q -s tests/game/test_daily_arena_golden_extended_messaging.py tests/workers/test_messaging_delivery_units.py tests/services/test_telegram_delivery.py tests/db/repo/test_production_reliability_repo.py tests/db/repo/test_production_reliability_blocked_candidates.py tests/services/test_production_invariants.py tests/workers/test_telegram_delivery_outcomes_units.py` -> `52 passed`.
- Exact failed CI test scope with local capture disabled: `.venv/bin/python -m pytest -q -s --ignore=tests/integration` with CI env -> `2140 passed, 1 skipped`. The same command without `-s` currently aborts before tests in this WSL environment with pytest capture `FileNotFoundError`; earlier Stage 0 reproduced the real CI failure before code fixes.
- Targeted reliability/payment subset: `.venv/bin/python -m pytest -q tests/scripts/test_payment_reliability_checks.py tests/services/test_production_invariants.py tests/services/test_telegram_delivery.py tests/db/repo/test_production_reliability_repo.py tests/workers/test_telegram_delivery_outcomes_units.py tests/workers/test_task_heartbeat.py tests/workers/test_premium_expiry_task.py tests/workers/test_daily_cup_messaging_orchestration_more.py tests/workers/test_tournaments_messaging.py tests/workers/test_tournament_task_entrypoints_units.py` -> `70 passed`.
- `ruff check app tests scripts` -> PASS.
- `black --check app tests scripts` -> PASS.
- `isort --check-only app tests scripts` -> PASS.
- `mypy app tests` -> PASS, `Success: no issues found in 1365 source files`.
- `git diff --check` -> PASS.
- `CI=1 FORCE_GROWTH_CHECK=1 BASE_REF=origin/main bash scripts/check_line_limits.sh` -> FAIL. Root cause is PR-wide changed app files over the hard local line gate, including pre-existing PR files outside this blocker pass (`app/db/repo/entitlements_repo.py`, `app/workers/task_heartbeat.py`, `app/workers/tasks/daily_cup_registration_push.py`) and touched PR reliability files (`app/db/repo/production_reliability_repo.py`, `app/services/production_invariants.py`, `app/services/telegram_delivery.py`, `app/workers/tasks/daily_cup_messaging_delivery.py`, `app/workers/tasks/tournaments_messaging_delivery.py`). This blocker was not bypassed and line limits were not changed.

### Agent statuses

- Agent B Scope/Safety Controller: PASS on current tracked diff; no forbidden prod/config/secret/deploy/migration scope detected; no payment reliability runtime regression detected.
- Agent C Code Reviewer: PASS for correctness after patches. Prior blockers were stale replay duplicate-send risk, current-phase gap masking, and test formatting/mypy/test-line fallout; all were patched. Known separate blocker: PR-wide line-limit gate.
- Agent D Invariant Auditor: PASS for invariant/behavioral evidence after row-based tests were added. Packaging caveat: `tests/db/repo/test_production_reliability_blocked_candidates.py` is currently untracked and must be included in any eventual commit/push. Known separate blocker: PR-wide line-limit gate.
- Agent E Final Acceptance Gate: `BLOCKED`, because the forced line-limit gate is red and no push/GitHub green CI happened.

### GitHub state after local fix pass

- PR #246: open, draft, not merged, mergeable, remote head `8769e765268d9761481eb8685a065b5570917754`, base `main` at `bafcf2730211355e66718d3dbb43b94e69424bca`.
- GitHub Actions on remote head: `lint_unit` completed `failure`; `integration` and `tournament_regression` completed `skipped`.
- Review threads via GitHub connector: `0` review threads returned in the latest read-only query.
- No branch push was performed after local fixes because local gates are not all green.

### Current blocker

- Status remains `BLOCKED_ON_LINE_LIMIT_GATE` until the exact forced line-limit gate passes or the owner approves a separate size-remediation scope. No branch push was performed after this fix pass because local gates are not all green.

## PR #246 line-limit closure pass - 2026-07-10

Status: `LOCAL_GATES_GREEN_PENDING_COMMIT_PUSH`.

### Stage 0 - forced line-limit failure evidence

- Exact command: `CI=1 FORCE_GROWTH_CHECK=1 BASE_REF=origin/main bash scripts/check_line_limits.sh`.
- Script rules verified from `scripts/check_line_limits.sh`: changed `app/**/*.py` files fail above `250` lines and also fail above `220` lines without `[APPROVED_SIZE_EXCEPTION]`; changed `tests/**/*.py` files fail above `400` lines; changed `tools/**/*.py` files fail above `300` lines. The script was read only and was not changed.
- Git state at reproduction: local branch `feature/production-critical-flows-reliability`; local `HEAD` and remote PR head were both `8769e765268d9761481eb8685a065b5570917754`; `origin/main` was `bafcf2730211355e66718d3dbb43b94e69424bca`.

Failing changed files:

| File | Kind | Lines | Effective limit | Touched in PR | Split required |
| --- | --- | ---: | ---: | --- | --- |
| `app/db/repo/entitlements_repo.py` | app | 236 | 220/250 | yes | yes |
| `app/db/repo/production_reliability_repo.py` | app | 499 | 220/250 | yes | yes |
| `app/services/production_invariants.py` | app | 547 | 220/250 | yes | yes |
| `app/services/telegram_delivery.py` | app | 295 | 220/250 | yes | yes |
| `app/workers/task_heartbeat.py` | app | 287 | 220/250 | yes | yes |
| `app/workers/tasks/daily_cup_messaging_delivery.py` | app | 277 | 220/250 | yes | yes |
| `app/workers/tasks/daily_cup_registration_push.py` | app | 224 | 220/250 | yes | yes |
| `app/workers/tasks/tournaments_messaging_delivery.py` | app | 297 | 220/250 | yes | yes |

Current untracked blocked-candidate test file line count:
- `tests/db/repo/test_production_reliability_blocked_candidates.py`: `175` lines, tests file, under the `400` line limit, must be included in the final commit.

Exact failed output:

```text
WARNING: app file over 200 lines (203): app/api/routes/admin/overview_series.py
WARNING: app file over 200 lines (202): app/api/routes/internal_analytics.py
WARNING: app file over 200 lines (218): app/bot/handlers/gameplay.py
WARNING: app file over 200 lines (202): app/bot/handlers/gameplay_flows/friend_series_flow_best3_runtime.py
WARNING: app file over 200 lines (213): app/bot/handlers/payments_runtime.py
WARNING: app file over 200 lines (208): app/bot/handlers/referral.py
WARNING: app file over 200 lines (220): app/bot/texts/de.py
WARNING: app file over 200 lines (215): app/core/global_best_streak_cache.py
WARNING: app file over 200 lines (236): app/db/repo/entitlements_repo.py
WARNING: app file over 200 lines (226): app/db/repo/outbox_events_repo.py
WARNING: app file over 200 lines (499): app/db/repo/production_reliability_repo.py
WARNING: app file over 200 lines (201): app/db/repo/promo_repo_redemptions.py
WARNING: app file over 200 lines (216): app/db/repo/tournament_matches_repo.py
WARNING: app file over 200 lines (211): app/economy/energy/energy_consume_quiz.py
WARNING: app file over 200 lines (219): app/game/arena_duels/accept.py
WARNING: app file over 200 lines (203): app/game/duels/limits_service_api.py
WARNING: app file over 200 lines (203): app/game/sessions/service/friend_challenges_create.py
WARNING: app file over 200 lines (220): app/game/sessions/service/friend_challenges_series.py
WARNING: app file over 200 lines (204): app/game/sessions/service/sessions_start_daily.py
WARNING: app file over 200 lines (212): app/game/sessions/service/sessions_submit_daily.py
WARNING: app file over 200 lines (210): app/game/tournaments/settlement.py
WARNING: app file over 200 lines (213): app/services/payment_reconciliation.py
WARNING: app file over 200 lines (547): app/services/production_invariants.py
WARNING: app file over 200 lines (295): app/services/telegram_delivery.py
WARNING: app file over 200 lines (207): app/workers/tasks/arena_duels_notification_delivery.py
WARNING: app file over 200 lines (277): app/workers/tasks/daily_cup_messaging_delivery.py
WARNING: app file over 200 lines (204): app/workers/tasks/daily_cup_proof_cards_delivery.py
WARNING: app file over 200 lines (224): app/workers/tasks/daily_cup_registration_push.py
WARNING: app file over 200 lines (214): app/workers/tasks/daily_cup_turn_reminder_delivery.py
WARNING: app file over 200 lines (792): app/workers/tasks/payments_reliability_async.py
WARNING: app file over 200 lines (297): app/workers/tasks/tournaments_messaging_delivery.py
WARNING: app file over 200 lines (215): app/workers/tasks/tournaments_proof_cards.py
WARNING: app file over 200 lines (204): app/workers/tasks/tournaments_proof_cards_delivery.py
WARNING: app file over 200 lines (204): app/workers/tasks/tournaments_proof_cards_sender.py
WARNING: app file over 200 lines (287): app/workers/task_heartbeat.py
ERROR: app file exceeds 220 lines without [APPROVED_SIZE_EXCEPTION] (236): app/db/repo/entitlements_repo.py
ERROR: app file exceeds 250 lines (499): app/db/repo/production_reliability_repo.py
ERROR: app file exceeds 220 lines without [APPROVED_SIZE_EXCEPTION] (499): app/db/repo/production_reliability_repo.py
ERROR: app file exceeds 250 lines (547): app/services/production_invariants.py
ERROR: app file exceeds 220 lines without [APPROVED_SIZE_EXCEPTION] (547): app/services/production_invariants.py
ERROR: app file exceeds 250 lines (295): app/services/telegram_delivery.py
ERROR: app file exceeds 220 lines without [APPROVED_SIZE_EXCEPTION] (295): app/services/telegram_delivery.py
ERROR: app file exceeds 250 lines (287): app/workers/task_heartbeat.py
ERROR: app file exceeds 220 lines without [APPROVED_SIZE_EXCEPTION] (287): app/workers/task_heartbeat.py
ERROR: app file exceeds 250 lines (277): app/workers/tasks/daily_cup_messaging_delivery.py
ERROR: app file exceeds 220 lines without [APPROVED_SIZE_EXCEPTION] (277): app/workers/tasks/daily_cup_messaging_delivery.py
ERROR: app file exceeds 220 lines without [APPROVED_SIZE_EXCEPTION] (224): app/workers/tasks/daily_cup_registration_push.py
ERROR: app file exceeds 250 lines (297): app/workers/tasks/tournaments_messaging_delivery.py
ERROR: app file exceeds 220 lines without [APPROVED_SIZE_EXCEPTION] (297): app/workers/tasks/tournaments_messaging_delivery.py
```

### Stage 1 - line-limit extraction summary

Extraction was mechanical and compatibility-preserving:

- `app/db/repo/production_reliability_repo.py` is now a thin facade over focused repo modules:
  `telegram_delivery_attempts_repo.py`, `telegram_blocked_candidates_repo.py`,
  `worker_task_heartbeats_repo.py`, `production_invariant_alerts_repo.py`, and
  `production_reliability_types.py`.
- `app/services/production_invariants.py` is now a thin facade over
  `app/services/production_invariant_checks/` builders and runner modules.
- `app/services/telegram_delivery.py` keeps the public import path and delegates types,
  exception classification, retry gating, and skipped-record helpers to focused modules.
- `app/workers/tasks/daily_cup_messaging_delivery.py` delegates target/version/result helpers
  to `daily_cup_messaging_delivery_targets.py`.
- `app/workers/tasks/tournaments_messaging_delivery.py` delegates target/version helpers and
  message payload assembly to focused modules.
- `app/workers/task_heartbeat.py` delegates the static critical heartbeat registry to
  `task_heartbeat_registry.py`.
- `app/workers/tasks/daily_cup_registration_push.py` delegates delivery target construction to
  `daily_cup_registration_push_targets.py`.
- `app/db/repo/entitlements_repo.py` inherits expiry-only methods from
  `premium_entitlements_expiry_repo.py`.

Behavior-preservation checks:

- Delivery idempotency/replay semantics preserved through the existing public
  `app.services.telegram_delivery` facade; repo monkeypatch compatibility was explicitly restored.
- Daily Cup and private tournament target IDs still include user, phase/content version, and
  operation keys.
- Heartbeat registry values were moved without changing task names, schedule keys, stale windows,
  severity, or enabled flags.
- Invariant check SQL/severity/correlation helpers were moved without changing alert open/resolve
  semantics.
- Premium expiry count/update SQL was moved behind inherited `EntitlementsRepo` methods.

### Stage 2 - local gate evidence after extraction

- Initial no-capture targeted pytest issue: `.venv/bin/python -m pytest -q tests/db/repo/test_production_reliability_repo.py tests/db/repo/test_production_reliability_blocked_candidates.py tests/workers/test_task_heartbeat.py tests/workers/test_production_invariant_alerts_task.py` aborted before tests with pytest capture cleanup `FileNotFoundError` in `_pytest/capture.py::snap`; rerun with `-s` passed. This matches the known local WSL capture issue and was not used as a green signal.
- Repo/heartbeat/alert targeted suite: `.venv/bin/python -m pytest -q -s tests/db/repo/test_production_reliability_repo.py tests/db/repo/test_production_reliability_blocked_candidates.py tests/workers/test_task_heartbeat.py tests/workers/test_production_invariant_alerts_task.py` -> `20 passed`.
- Invariant/script targeted suite: `.venv/bin/python -m pytest -q -s tests/services/test_production_invariants.py tests/scripts/test_production_critical_invariants.py tests/workers/test_production_invariant_alerts_task.py` -> `20 passed`.
- Telegram delivery targeted suite: `.venv/bin/python -m pytest -q -s tests/services/test_telegram_delivery.py tests/workers/test_telegram_delivery_outcomes_units.py tests/workers/test_messaging_delivery_units.py tests/workers/test_daily_cup_registration_push_units.py` -> `22 passed`.
- Worker messaging targeted suite: `.venv/bin/python -m pytest -q -s tests/workers/test_messaging_delivery_units.py tests/workers/test_telegram_delivery_outcomes_units.py tests/workers/test_tournament_task_entrypoints_units.py` -> `11 passed`.
- Heartbeat/invariant targeted suite: `.venv/bin/python -m pytest -q -s tests/workers/test_task_heartbeat.py tests/services/test_production_invariants.py` -> `19 passed`.
- Daily Cup registration push targeted suite: `.venv/bin/python -m pytest -q -s tests/workers/test_daily_cup_registration_push_units.py tests/workers/test_daily_cup_schedule.py tests/workers/test_daily_cup_prestart_reminder.py` -> `10 passed`.
- Premium expiry targeted suite: `.venv/bin/python -m pytest -q -s tests/db/repo/test_entitlements_expiry_repo.py tests/workers/test_premium_expiry_task.py` -> `6 passed`.
- Focused blocker suite: `.venv/bin/python -m pytest -q -s tests/game/test_daily_arena_golden_extended_messaging.py tests/workers/test_messaging_delivery_units.py tests/services/test_telegram_delivery.py tests/db/repo/test_production_reliability_repo.py tests/db/repo/test_production_reliability_blocked_candidates.py tests/services/test_production_invariants.py tests/workers/test_telegram_delivery_outcomes_units.py` -> `52 passed`.
- Targeted reliability/payment subset: `.venv/bin/python -m pytest -q -s tests/scripts/test_payment_reliability_checks.py tests/services/test_production_invariants.py tests/services/test_telegram_delivery.py tests/db/repo/test_production_reliability_repo.py tests/workers/test_telegram_delivery_outcomes_units.py tests/workers/test_task_heartbeat.py tests/workers/test_premium_expiry_task.py tests/workers/test_daily_cup_messaging_orchestration_more.py tests/workers/test_tournaments_messaging.py tests/workers/test_tournament_task_entrypoints_units.py` -> `76 passed`.
- Payment reliability checker tests: `.venv/bin/python -m pytest -q -s tests/scripts/test_payment_reliability_checks.py` -> `20 passed`.
- Full non-integration pytest: `.venv/bin/python -m pytest -q -s --ignore=tests/integration` -> `2140 passed, 1 skipped`.
- Ruff: `.venv/bin/ruff check app tests scripts` -> PASS.
- Black: `.venv/bin/black --check app tests scripts` -> PASS.
- isort: `.venv/bin/isort --check-only app tests scripts` -> PASS.
- Mypy: `.venv/bin/mypy app tests` -> `Success: no issues found in 1389 source files`.
- Diff whitespace: `git diff --check` -> PASS.
- Forced line gate: `CI=1 FORCE_GROWTH_CHECK=1 BASE_REF=origin/main bash scripts/check_line_limits.sh` -> PASS. Output contained soft `WARNING: app file over 200 lines` lines only and no `ERROR:` lines.

### Stage 3 - current local packaging state

- `tests/db/repo/test_production_reliability_blocked_candidates.py` remains required and is under the `400` line test-file limit (`175` lines before formatting pass).
- Bare `ruff`, `black`, and `isort` commands are not on this shell `PATH`; the same tools were run through `.venv/bin/...`.
- No `.env*`, secrets, deploy config, `.github/workflows/**`, `deploy/**`, `docker-compose.prod.yml`, or migration files were modified in this extraction pass.

Full gate results are recorded in the final PR report.
