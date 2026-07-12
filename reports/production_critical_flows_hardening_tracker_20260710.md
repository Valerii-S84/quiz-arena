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

## PR #246 Delivery Reliability State Machine Matrix

Agent A implementation lock: code changes remain blocked until Agent C reviews this section
and returns `PASS`.

Agent B scope/safety controller status: `PASS` for scope boundaries. Allowed write scope is
limited to the current Codex findings, directly related regression tests, this tracker, and the
premium-expiry runbook/config code needed to keep the schedule default-off. Forbidden scope remains
deploy, production writes/migrations/restarts, task replay, manual messaging, `.env*`, secrets,
production config, `docker-compose.prod.yml`, merge, draft removal, auto-recovery enablement, live
reconciliation enablement, dependency/CI changes, migrations, broad refactor, and unrelated
product behavior changes.

### Matrix 1: Delivery attempt lifecycle

Policy constants:
- retryable failure codes: `TELEGRAM_RETRY_AFTER` only.
- permanent/non-retryable failure codes: `TELEGRAM_FORBIDDEN`,
  `TELEGRAM_BAD_REQUEST`, `TELEGRAM_BLOCKED_CANDIDATE`, `MISSING_CHAT_ID`,
  `EDIT_REPLACED_BY_FALLBACK_SEND`, `DUPLICATE_DELIVERY_ATTEMPT`, and unknown
  non-policy failures unless explicitly reclassified later.
- stale pending retry policy: only `PENDING` rows with
  `safe_context.pending_replay_safe = true`, `updated_at <= now - STALE_PENDING_AFTER`,
  and `attempt_count < MAX_DELIVERY_ATTEMPTS`.
- terminal statuses: `SENT`, `FAILED`, `SKIPPED`.

| State | `prepare_telegram_delivery.should_send` | Attempt count | Row create/update | Skipped return | Alert/checker | Tests |
| --- | --- | --- | --- | --- | --- | --- |
| no row + chat id | `True` | no increment until `mark_sent`/`mark_failed` | create `PENDING` row | no | no alert until terminal failure or stale invariant | `tests/services/test_telegram_delivery.py::test_prepare_delivery_creates_pending_attempt` |
| no row + no chat id | `False` | no send increment | create row then mark `SKIPPED` | yes, `MISSING_CHAT_ID` | terminal outcome prevents zero-outcome gap | `tests/services/test_telegram_delivery.py` missing-chat coverage |
| `PENDING` fresh, unsafe send | `False` | unchanged | existing row unchanged | no | stale checker may alert only after policy window | `tests/services/test_telegram_delivery.py::test_stale_pending_send_delivery_without_safe_context_does_not_retry` |
| `PENDING` stale, safe edit/replay | `True` only after claim | unchanged at claim; terminal marker increments | update claim to fresh `PENDING` | no | retry bounded by age/attempts | `test_stale_pending_delivery_allows_controlled_retry` |
| `PENDING` stale, unsafe | `False` | unchanged | unchanged | no | invariant/checker can expose stale row | `test_stale_pending_send_delivery_without_safe_context_does_not_retry` |
| `SENT` | `False` | unchanged | unchanged | duplicate is blocked by idempotency | no new alert | repair planner duplicate exact-phase test |
| `FAILED` retryable | `True` if `failure_code in RETRYABLE_FAILURE_CODES`, not blocked, and attempts below max | terminal retry send increments on next mark | claim to `PENDING`, then terminal update | no | still visible as failed until retry succeeds | retryable repair planner + delivery retry tests |
| `FAILED` non-retryable | `False` | unchanged | unchanged | no | failed terminal counts as durable outcome; repair excludes replay | permanent failure repair tests |
| `FAILED` blocked | `False` for active blocked candidate | new same-user target is created and marked `SKIPPED` when active block is present | create/update `SKIPPED` for current target | yes, `TELEGRAM_BLOCKED_CANDIDATE` | blocked-user active-only checker counts only active candidates | blocked lifecycle tests |
| `SKIPPED` | `False` | unchanged | unchanged | yes/terminal | not replayable; counts as durable outcome | skipped repair tests |
| max attempts reached | `False` | unchanged | unchanged | no | remains terminal failed, not safe replay | retry bounded SQL tests |

Invariant protected: every expected delivery key has at most one send in flight, terminal rows are
durable outcomes, and retry is limited to explicit retryable failures or explicitly safe stale edit
attempts.

### Matrix 2: Edit + fallback send lifecycle

Key rule: once an edit attempt row is created, fallback handling must not leave that original edit
attempt `PENDING` forever. After a completed fallback path it must be `SENT`, `FAILED`, `SKIPPED`,
or an explicitly retryable stale `PENDING` governed by timestamp/attempt policy.

| Scenario | Original edit attempt final status | Fallback attempt final status | Any lingering `PENDING`? | Retry allowed | Alert/checker visibility | Tests |
| --- | --- | --- | --- | --- | --- | --- |
| edit succeeds | `SENT` | no row | no | no | durable outcome present | existing Daily Cup/private messaging tests |
| edit returns not-modified | `SENT` | no row | no | no | durable outcome present | `test_deliver_round_messages_counts_not_modified_as_edited` |
| edit fails, fallback send succeeds | `SKIPPED` with `EDIT_REPLACED_BY_FALLBACK_SEND` | `SENT` | no | no | current phase has terminal outcome | Daily Cup and private fallback-success regression tests |
| edit fails, fallback send fails retryable | `FAILED`; `failure_code` mirrors fallback retryable code and `failure_reason` starts with `fallback_send_failed_after_edit_failed` | `FAILED` with `TELEGRAM_RETRY_AFTER` | no | fallback retry only if retryable policy allows; original edit is not replay-safe | checker sees terminal failure, no stale pending gap | new Daily Cup/private retryable failure tests |
| edit fails, fallback send fails permanent forbidden | `FAILED`; `failure_code=TELEGRAM_FORBIDDEN`, `failure_reason=fallback_send_failed_after_edit_failed` | `FAILED` with `TELEGRAM_FORBIDDEN`, blocked candidate true | no | no safe replay | repair planner excludes permanent failed fallback; blocked checker counts active candidate only | new Daily Cup/private permanent forbidden tests |
| edit fails, fallback send fails permanent bad request/chat not found | `FAILED`; `failure_code=TELEGRAM_BAD_REQUEST`, `failure_reason=fallback_send_failed_after_edit_failed` | `FAILED` with `TELEGRAM_BAD_REQUEST`, blocked candidate according to classifier | no | no safe replay | repair planner excludes permanent failed fallback | new Daily Cup/private permanent bad-request tests |
| edit fails, fallback send fails unknown nonretryable | `FAILED`; `failure_code=TELEGRAM_SEND_ERROR`, `failure_reason=fallback_send_failed_after_edit_failed` | `FAILED` with `TELEGRAM_SEND_ERROR` | no | no safe replay until code explicitly classifies it retryable | failed outcome is terminal; repair excludes unsafe replay | new Daily Cup/private generic failure tests |
| edit fails, fallback skipped blocked | `SKIPPED` with blocked/fallback-skipped reason | `SKIPPED` blocked | no | no while active blocked candidate remains | blocked checker active-only; delivery gap has durable outcome | blocked fallback skip test if implemented in delivery unit tests |
| fallback succeeds but mark sent fails after real send | original edit attempt is not marked terminal by the worker; task path must surface failure rather than report success | fallback may remain `PENDING`, but `safe_context.pending_replay_safe` must be false | possible infrastructure `PENDING`, but not replay-safe | no automatic resend of fallback, because the real send may already have happened | stale pending/checker exposes the gap for manual audit instead of duplicate send | mark-sent failure test if this branch is changed; duplicate-send invariant blocks retry |
| original edit attempt exists `PENDING` from earlier safe edit | `prepare` may claim only when stale and safe | fallback row created only after claimed edit fails again | no permanent pending after fallback terminal path | bounded by safe stale policy | stale pending and terminal rows visible | stale pending retry tests |
| fallback attempt exists `PENDING` | no new duplicate fallback send unless retry policy claims it | claim only if stale and policy allows; otherwise unchanged | possible only under explicit stale policy | bounded | checker can see stale pending | delivery retry tests |
| fallback attempt exists `FAILED` retryable | original already terminal or stale-safe | fallback may retry if code is retryable and attempts below max | no new original pending | fallback retry only | repair planner may include retryable failed fallback | repair planner retryable failure test |
| fallback attempt exists `SENT` | original edit becomes/has `SKIPPED` | `SENT` | no | no | duplicate fallback blocked | fallback duplicate/SENT skip test |

Invariant protected: edit failure plus fallback failure is a terminal durable-outcome path, not a
silent stale `PENDING` leak.

### Matrix 3: Phase/version idempotency

Daily Cup target contract:
- flow: `daily_cup_round_messaging`.
- correlation_id: tournament id.
- target_type: `user`.
- target_id: `{user_id}:phase:{content_version}:{operation}`.
- content_version: `round:{current_round}:status:{status}` or `status:completed` or
  `status:canceled`.
- operations: `send`, `edit:{message_id}`, `fallback_send_after_edit:{message_id}`.
- idempotency key:
  `telegram-delivery:{flow}:{correlation_id}:user:{target_id}`.

Private tournament target contract:
- flow: `private_tournament_round_messaging`.
- correlation_id: tournament id.
- target_type: `user`.
- target_id: `{user_id}:phase:{content_version}:{operation}`.
- content_version: `round:{current_round}:status:{status}` or `status:completed`.
- operations and idempotency key follow the same shape as Daily Cup.

| Dimension | Daily Cup rule | Private tournament rule | Duplicate block | New phase sends again | Repair/checker target | Tests |
| --- | --- | --- | --- | --- | --- | --- |
| tournament id | correlation_id is cup id | correlation_id is private tournament id | same tournament + same target blocks duplicate | different tournament sends independently | checker filters by flow + correlation_id | target builder tests / invariant SQL tests |
| user id | first target segment, never collapsed alone for repair | same | exact same user+phase+operation only | same user new phase is distinct | repair must preserve full `target_id` | repair phase-specific tests |
| operation | send/edit/fallback are distinct | same | same operation blocks exact duplicate | fallback send is distinct from edit | fallback terminal rows still count for phase via prefix match | fallback tests |
| message id | edit/fallback include message id | same | same message id exact operation blocks duplicate | changed message id creates a new operation key | checker phase prefix ignores operation suffix | invariant SQL current-phase tests |
| round number | embedded in `round:{n}` | embedded in `round:{n}` | round 1 `SENT` does not block round 2 | round change sends again | missing current round visible | current-phase gap tests |
| tournament status | embedded in status | embedded in status | same status+round duplicate blocked | status transition sends again | completed current phase checked separately | completed tests to add for long-running tournaments |
| Daily Cup invite/registration push | flow is derived from sent event type, correlation_id is cup id, target_type `user`, target_id `{user_id}` | not used for private tournament | same invite flow+cup+user only | round/final/cancel flows are separate and send again | zero-outcome checker may include relevant Daily Cup flows, repair planner remains round-flow scoped | registration push tests |
| Daily Cup last-call/prestart reminder | same registration-push target contract with distinct flow from event type | not used for private tournament | same reminder flow+cup+user only | invite vs reminder vs round are distinct flows | delivery attempts are durable per flow | existing reminder/push tests |
| Daily Cup turn reminder | flow `daily_cup_turn_reminder`, correlation_id cup id, target_type `challenge_user`, target_id `{challenge_id}:{target_user_id}` | not used for private tournament | same challenge+target user only | next challenge/user target sends independently | checker zero-outcome includes turn-reminder flow; repair planner does not collapse into round target | turn reminder delivery tests |
| Daily Cup final | same `daily_cup_round_messaging` flow with content_version `status:completed` and operation suffix | not used for private tournament | exact completed target only | completed phase sends even if round phase was sent | current phase prefix is `user:phase:status:completed:%` | completed/current-phase tests |
| Daily Cup cancel | flow `daily_cup_cancel_message`, correlation_id cup id, target_type `chat_hash`, target_id `{hash_chat_id(chat_id)}:status:canceled` | not used for private tournament | same cancel chat hash only | cancel is separate from invite/round/final | cancel delivery terminal row is separate from round repair targets | cancel delivery tests |
| private tournament invite/reminder | not Daily Cup | no durable Telegram target is introduced by this PR for private invite/reminder; no code path may infer these from round outcomes | n/a | future implementation must use distinct flow/phase keys | out of current Codex findings unless a current flow expects it | n/a |
| private tournament final | not Daily Cup | same `private_tournament_round_messaging` flow with content_version `status:completed` and operation suffix | exact completed target only | completed phase sends even if prior round was sent | current phase prefix is `user:phase:status:completed:%` | completed/current-phase tests |
| private tournament cancel | not Daily Cup | no implemented private cancel delivery target in this PR; private canceled tournaments are excluded from round messaging context | n/a | future cancel messaging must use a distinct flow/phase key and cannot be suppressed by round `SENT` | not part of current repair planner/checker scope until delivery target exists | explicit no-current-scope note |
| standings edit | operation `edit:{message_id}` | same | exact edit duplicate blocked | new round/status edit sends again | current phase prefix match | target builder tests |
| fallback send | operation `fallback_send_after_edit:{message_id}` | same | exact fallback duplicate blocked | fallback distinct from original edit | original edit terminalized separately | fallback tests |

Invariant protected: previous `SENT` for round 1 or for a user prefix cannot suppress round 2,
final, cancel, or any current phase. Only exact same flow/correlation/user/phase/operation is
idempotent.

### Matrix 4: Blocked user lifecycle

Active blocked policy must match delivery skip logic and checker logic:
`FAILED is_blocked_candidate = true` is active only when its blocked timestamp is within
`BLOCKED_CANDIDATE_TTL` and no `users.last_seen_at` is newer than that blocked timestamp.

| State | Future send allowed | Future send skipped | Active alert count | Checker behavior | Tests |
| --- | --- | --- | --- | --- | --- |
| never blocked | yes | no | no | not counted | normal prepare tests |
| blocked candidate fresh | no for same Telegram user id | yes, current target becomes `SKIPPED` blocked | yes | counted once by distinct telegram user id, no raw sensitive output | blocked candidate tests |
| blocked candidate expired by TTL | yes | no | no | not counted | TTL expiry tests |
| blocked candidate superseded by newer inbound activity | yes | no | no | not counted | newer `users.last_seen_at` tests |
| blocked candidate after `/start` | yes after `last_seen_at` update | no | no | old candidate suppressed/resolved by checker OK result | recovered-user tests |
| non-blocking Telegram error | policy-dependent normal retry/failure | no blocked skip | no blocked alert | not counted | non-blocking failure tests |
| permanent forbidden | no while active blocked candidate remains | yes | yes while active | counted as active blocked | forbidden classification tests |
| chat not found | no while active blocked candidate remains | yes when classified missing/blocked | yes while active | counted only while active | bad-request missing-chat tests |

Invariant protected: blocked users are not suppressed forever after inbound recovery, and historical
blocked rows remain audit evidence without keeping the active alert open forever.

### Matrix 5: Production invariant checker scope

| Check | Source tables | Cutoff logic | False positive guard | False negative guard | Severity | Tests |
| --- | --- | --- | --- | --- | --- | --- |
| Daily Cup per-participant current phase gap | `tournaments`, `tournament_participants`, `users`, `telegram_delivery_attempts` | recent Daily Cup window | active users only, exclude canceled, terminal statuses count | target prefix includes current round/status/completed phase | P1 | Daily Cup current-phase SQL tests |
| private tournament current phase gap | `tournaments`, `tournament_participants`, `telegram_delivery_attempts` | active statuses regardless of `created_at`; completed/canceled only when recently updated/relevant deadline in window | avoid ancient completed/canceled tournaments outside window | long-running active ROUND_3 and recently completed old tournaments included | P1 | new long-running private tests |
| long-running private tournament round | same plus `current_round`, status/update/deadline fields available in schema | status-driven for active rounds | no infinite ancient scan for terminal tournaments | active older-than-2-days still checked | P1 | new ROUND_3 old-created test |
| canceled below minimum participants | Daily Cup `tournaments`, canceled target chat set from participants/users, `telegram_delivery_attempts` with flow `daily_cup_cancel_message` | recent Daily Cup cancellation window only | do not scan private canceled tournaments or ancient canceled cups | if Daily Cup cancels for low participants and eligible chat targets exist, missing cancel terminal outcomes must be visible | P1 when added to checker scope; currently not widened unless current findings require it | cancel delivery tests; no new checker branch unless implemented in current scope |
| zero eligible users | `tournaments`, participants, users | recent/current active event window | do not alert when no eligible recipient exists | alert when expected recipients exist and zero outcomes | P1 | zero outcome tests |
| expected delivery zero outcomes | tournament + delivery attempts | same as corresponding flow scope | participant existence/eligibility required | no terminal outcome for expected flow fails | P1 | zero-outcome tests |
| stale streak per-user | `quiz_attempts`, `streak_state` | activity in last 6 hours | no recent activity OK | same-user missing/stale row fails; other user update cannot mask | P1 | per-user stale tests |
| blocked users active only | `telegram_delivery_attempts`, `users` | `BLOCKED_CANDIDATE_TTL` | newer inbound/expired/non-blocking rows excluded | fresh forbidden/chat-not-found counted | P2 | blocked lifecycle checker tests |
| permanent failure replay exclusion | delivery attempts + repair planner | no time cutoff in pure plan; flow/correlation scoped | terminal permanent failures not marked safe replay | retryable failures/missing targets remain visible | P2 operational repair safety | repair planner tests |

Alert lifecycle submatrix for P3 reopen counting:

| Alert state | `record_open` behavior | Count result | Duplicate insert/upsert? | Tests |
| --- | --- | --- | --- | --- |
| no existing alert | insert `OPEN` row | `1` | no | `test_invariant_alert_record_open_dedupes_by_type_key_status` |
| existing `OPEN` alert | conflict update same `OPEN` row | previous count + 1 | no new row | existing open-repeat test to keep/add |
| existing `RESOLVED` alert, no `OPEN` | reopen terminal row and return immediately | previous count + 1 | no second insert/upsert, no double count | `test_invariant_alert_record_open_returns_after_successful_reopen` |
| existing `ACKED` alert, no `OPEN` | reopen terminal row and return immediately | previous count + 1 | no second insert/upsert, no double count | acked reopen regression test to keep/add |

Invariant protected: checker output is read-only, privacy-safe, current-phase specific, avoids
ancient terminal false positives, and does not miss active long-running tournament gaps.

### Matrix 6: Premium expiry lifecycle

| State | Task import | Beat schedule | Writes allowed automatically | Manual/approved run | Tests |
| --- | --- | --- | --- | --- | --- |
| feature flag off/default | task is importable | schedule not registered | no | task body can still be called explicitly by operator/test | default-off schedule test + task body test |
| feature flag on | task is importable | `premium-expiry-lifecycle-hourly` registered | yes, only after explicit config/deploy decision | task body works | enabled schedule test |
| task imported by Celery | safe under default config | no schedule unless flag true | no default write loop | n/a | import/default test |
| beat schedule registered | only when flag true | hourly q_normal entry | controlled scheduled writes | n/a | enabled schedule test |
| expired `ACTIVE` entitlement | n/a | n/a | only when task invoked/scheduled with approval | mark `EXPIRED` idempotently | existing expiry repo/task tests |
| non-expired `ACTIVE` entitlement | n/a | n/a | not changed | remains active | existing entitlement expiry tests |
| expired already `EXPIRED` entitlement | n/a | n/a | not changed | remains expired | existing entitlement expiry tests |

Rules:
- `PREMIUM_EXPIRY_SCHEDULE_ENABLED=false` by default.
- If the flag is false, module import registers the Celery task but does not register the beat
  schedule.
- If the flag is true, the beat schedule is registered.
- Manual/approved execution is separate from import and remains possible through the explicit task.
- No `.env*`, production config, deploy config, or `docker-compose.prod.yml` changes in this PR.

Invariant protected: production deploy cannot accidentally start an entitlement write loop merely
because Celery imports the module.

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

## PR #246 final false-alert / missed-alert pass - 2026-07-12

Status: `LOCAL_GATES_GREEN_PENDING_COMMIT_PUSH_AND_GITHUB_CI`.

Scope: close only the six Codex findings from review commit `87483600b8` on PR #246.

### Findings and fixes

| Finding | Fix summary | Regression evidence |
| --- | --- | --- |
| P1 heartbeat checker false-alert on first deploy | `worker_task_heartbeat_stale` now uses checker/app-start grace for missing heartbeat rows, while existing stale rows and `consecutive_failures > 0` still fail. | `tests/services/test_production_invariant_final_edges.py`: empty table immediate OK, missing after grace fails, stale row fails, fresh success OK, consecutive failures fail. |
| P1 queue staleness false-alert from manual review outbox rows | Queue freshness excludes intentional `OPEN` `payments_telegram_stars_reconciliation_review` rows and documents the operator-owned review reason in safe context; real `NEW`/`PENDING`/`RETRY`/non-review `OPEN` rows still count. | `tests/services/test_production_invariant_final_edges.py`: old manual review OK, old retryable row fails, mixed manual+real counts only the real stuck row, empty queue OK. |
| P2 disabled premium expiry schedule still monitored | `get_critical_task_heartbeats()` includes `premium-expiry-lifecycle-hourly` only when `premium_expiry_schedule_enabled` is true. No beat schedule or config default was changed. | `tests/workers/test_task_heartbeat.py` and `tests/services/test_production_invariant_final_edges.py`: disabled registry excludes premium expiry and creates no stale check; enabled registry includes it and missing-after-grace fails. |
| P2 Daily Cup turn reminder idempotency not versioned per reminder window | Turn reminder delivery target ID now includes `window_key`, derived from the previous persisted `expires_last_chance_notified_at` (`initial` for first window). Later windows can send; duplicate same-window attempts stay idempotent. | `tests/workers/test_daily_cup_turn_reminder_delivery.py` plus existing turn reminder worker tests: first window sent, second window same user sent, duplicate same second window skipped, different user unaffected. |
| P2 repair planner treats `PENDING` attempts as safe replay | Repair planner now accounts for `PENDING` attempts separately, classifies stale pending attempts, and blocks safe replay when any pending attempt exists for the same target. Retryable `FAILED` remains replay-safe only when no `SENT`/`PENDING` target exists and retry policy allows it. | `tests/services/test_messaging_repair_planner.py`: absent target missing, fresh pending not replay, stale pending classified but not replay, pending blocks retryable failed replay, retryable failed replay allowed, permanent failed/SENT not replay. |
| P2 canceled Daily Cups excluded from cancel-message outcome check | Added `daily_cup_cancel_message_gap` for `CANCELED` Daily Cups with active target users. Round-message checks remain limited to active/completed rounds and do not false-alert canceled cups. | `tests/services/test_production_invariant_final_edges.py` and `tests/services/test_production_invariants.py`: canceled missing cancel outcome fails, terminal cancel outcome OK, no active target OK, canceled cup does not require round outcome. |

### Local gate evidence

- Initial `pytest` without `-s` hit the known local WSL pytest capture cleanup `FileNotFoundError`; the same suites were rerun with `.venv/bin/python -m pytest -q -s`.
- `.venv/bin/python -m pytest -q -s tests/services/test_production_invariant_final_edges.py tests/services/test_production_invariants.py` -> `34 passed`.
- `.venv/bin/python -m pytest -q -s tests/services/test_messaging_repair_planner.py` -> `12 passed`.
- `.venv/bin/python -m pytest -q -s tests/workers/test_daily_cup_turn_reminder_delivery.py tests/workers/test_daily_cup_turn_reminder_worker.py tests/workers/test_task_heartbeat.py tests/workers/test_premium_expiry_task.py` -> `13 passed`.
- `.venv/bin/python -m pytest -q -s tests/scripts/test_payment_reliability_checks.py` -> `20 passed`.
- `.venv/bin/python -m pytest -q -s tests/workers/test_daily_cup_core_async_units.py tests/workers/test_daily_cup_delivery_units_more.py tests/workers/test_daily_cup_messaging_orchestration_more.py` -> `8 passed`.
- `.venv/bin/python -m pytest -q -s tests/services/test_production_invariant_delivery_tournaments.py` -> `5 passed`.
- `.venv/bin/ruff check app tests scripts` -> PASS.
- `.venv/bin/black --check app tests scripts` -> PASS.
- `.venv/bin/isort --check-only app tests scripts` -> PASS.
- `.venv/bin/mypy app tests` -> `Success: no issues found in 1395 source files`.
- `git diff --check` -> PASS.
- `CI=1 FORCE_GROWTH_CHECK=1 BASE_REF=origin/main bash scripts/check_line_limits.sh` -> PASS with soft `WARNING:` lines only and no `ERROR:` lines.

### CI result

- GitHub CI after this pass: pending until the local commit is pushed.
- Required post-push checks: `lint_unit`, `integration`, `tournament_regression`.

### Agent statuses

- Agent A - Виконавець: PASS. Implemented only checker/registry/planner/delivery target logic and regression tests for the six listed findings.
- Agent B - Scope/Safety Controller: PASS locally. No `.env*`, secrets, production config, deploy files, workflow files, `docker-compose.prod.yml`, migrations, production writes, replay, messaging, auto-recovery, or live reconciliation changes.
- Agent C - Code Reviewer: PASS locally. Edge cases covered: first-deploy empty heartbeat table, disabled premium expiry registry, manual review outbox rows, repeated turn reminder windows, pending repair candidates, and canceled Daily Cup cancel-message checks.
- Agent D - Invariant Auditor: PASS locally. Each finding has at least one regression test, and P1 checks still fail for stale heartbeat, real stale queue rows, missing enabled heartbeat after grace, and missing cancel-message outcomes.
- Agent E - Final Gate: `BLOCKED_ON_GITHUB_CI_PENDING` until commit, push, and GitHub CI complete. Target final status after green CI: `CODE_READY_FOR_FINAL_ACCEPTANCE_AUDIT`.

### Production safety

- No deploy.
- No production DB writes.
- No production migrations.
- No production restarts.
- No task replay.
- No manual messaging.
- No `.env*`, secrets, production config, `docker-compose.prod.yml`, workflow, or deploy changes.
- PR not merged by this pass; draft/readiness state not changed by this pass.
