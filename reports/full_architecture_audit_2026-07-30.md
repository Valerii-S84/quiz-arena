# Quiz Arena Full Backend Architecture Research Audit

Status: `Research complete`

Audit date: `2026-07-30`

Repository snapshot:

- Branch: `main`
- `HEAD`: `e4c1e6721f60c746cb3c3666fb03264859af71cc`
- `origin/main`: `e4c1e6721f60c746cb3c3666fb03264859af71cc`
- Commit: `fix(payments): handle blank charges and expired premium (#272)`
- Working tree at research time: clean

This document records a read-only static architecture audit. Production runtime,
the complete test suite, build, deploy, external frontend, and external QuizBank
implementations were not executed or inspected. Findings distinguish direct
facts, high-confidence conclusions from code ordering/state, and tentative
runtime applicability.

The primary conclusion is that the transactional core has many strong database
invariants, but the largest risks are concentrated at `commit ↔ broker/Telegram`
boundaries, admin-auth session semantics, and hidden bidirectional dependencies
between `bot`, `workers`, and `game`.

## 1. Repository snapshot

| Field | Value |
|---|---|
| Branch | `main` |
| `HEAD` | `e4c1e6721f60c746cb3c3666fb03264859af71cc` |
| `origin/main` | `e4c1e6721f60c746cb3c3666fb03264859af71cc` |
| Commit | `fix(payments): handle blank charges and expired premium (#272)` |
| Working tree | clean |
| Audit date | `2026-07-30` |

## 2. Coverage ledger

Static coverage:

- `1,692` tracked files.
- `745` production Python modules; all parsed successfully by AST.
- `625` test files and `2,202` test functions.
- `60` Alembic revisions: one root and one head, `d7e8f9a0b123`.
- `42` ORM tables.
- `27` scripts, `14` tools, `22` docs, and `1` GitHub workflow.
- `2,302` production functions/methods and `412` classes.
- `2,629` internal import edges when local imports are included.
- `125` `SessionLocal.begin()` occurrences in `71` files.
- `40` registered Celery tasks, `32` beat entries, and `29` distinct scheduled
  entrypoints.

Production modules by package:

| Package | Files |
|---|---:|
| `app/api` | 87 |
| `app/bot` | 154 |
| `app/core` | 11 |
| `app/db` | 122 |
| `app/economy` | 83 |
| `app/game` | 133 |
| `app/services` | 38 |
| `app/workers` | 115 |
| root `app` | 2 |

Heuristic role classification:

| Role | Modules |
|---|---:|
| Application orchestration | 144 |
| Telegram presentation/handlers | 106 |
| HTTP/API routes | 81 |
| Domain policy/rules | 76 |
| Persistence repositories | 75 |
| Workers/tasks | 75 |
| ORM models | 44 |
| Delivery/messaging | 43 |
| Rendering/text | 30 |
| Configuration/composition | 10 |
| Observability/health | 10 |
| External integrations | 5 |
| Framework entrypoints | 2 |
| Package facades or mixed/unclear | 44 |

Tests by area:

| Area | Files |
|---|---:|
| API | 44 |
| Bot | 85 |
| DB | 34 |
| Economy | 61 |
| Game | 133 |
| Integration | 120 |
| Scripts | 12 |
| Services | 22 |
| Tools | 7 |
| Workers | 91 |
| Root | 16 |

Tests directly import `278/745` production modules. This is a lower bound, not a
coverage percentage: facade imports and behavioral integration tests do not
always import an implementation module directly.

## 3. Runtime topology

```text
Telegram
   │ webhook update
   ▼
Caddy ──► FastAPI/Uvicorn (4 workers)
             │
             ├─► durable payment evidence ─► PostgreSQL
             ├─► enqueue update ───────────► Redis/Celery
             │                                  │
             │                                  ▼
             │                            Celery worker
             │                                  │
             │                                  ▼
             │                         aiogram Dispatcher
             │                                  │
             └──────────────────── handlers/domain/economy
                                                │
                                   PostgreSQL / Redis / Telegram

Celery Beat ─► Redis queues ─► q_high / q_normal / q_low workers

Browser ─► Caddy ─► backend API/admin/ops
                ├─► standalone frontend container
                └─► standalone QuizBank API container
```

Webhook chain:

```text
telegram_webhook
  → payment-evidence transaction
  → process_telegram_update
  → processing-slot transaction
  → aiogram dispatch
  → bot handlers
```

Payment evidence is written before enqueue. Evidence or enqueue failure returns
`503`. Invalid secret/JSON/missing `update_id` returns `200 ignored`.

Health semantics:

- `/live` checks the process only.
- `/ready` checks DB and Redis.
- `/health` checks DB, Redis, and Celery.
- Production healthcheck uses `/ready`, so a Celery outage intentionally does
  not remove API readiness.

## 4. Current package and dependency map

Unique module-to-module edges between packages:

| Source | Main outbound dependencies |
|---|---|
| `api` | `db` 105, `services` 33, `core` 22, `economy` 11, `workers` 3 |
| `bot` | `game` 133, `db` 34, `economy` 33, `core` 24, `services` 21, `workers` 11 |
| `game` | `db` 150, `core` 24, `economy` 13, `workers` 4 |
| `economy` | `db` 101, `core` 5, `services` 1 |
| `services` | `db` 18, `core` 15, `economy` 9, `api` 2, `game` 2 |
| `workers` | `db` 126, `game` 42, `bot` 39, `core` 28, `services` 19, `economy` 11 |
| `db` | `game` 3, `core` 1 |
| `core` | `db` 2 |

Largest inbound hubs:

- `app/bot/texts/de.py`: 87 importers.
- `app/db/session.py`: 81.
- `app/core/config.py`: 70.
- Game session types/errors: 44/42.

The explicit top-level graph without `__init__.py` has `0` strongly connected
components. Adding local imports creates cycles; the shortest confirmed
cross-layer cycle is `bot → workers → bot`. Package initializers separately
create re-export SCCs in admin, gameplay flows, and keyboards, but static
analysis does not prove an import-time exception.

## 5. Feature ownership map

| Feature | Entry/presentation | Core orchestration | Persistence/async |
|---|---|---|---|
| Regular/Daily quiz | `bot/handlers/gameplay*` | `game/sessions/service` | quiz sessions, attempts, daily runs, energy, ledger |
| Friend challenges | friend lobby/answer flows | `game/friend_challenges`, session service | friend rows, quiz sessions, proof/notification workers |
| Arena | gameplay Arena flows | `game/arena_duels` | duels/attempts, analytics, notification workers |
| Private tournaments | gameplay tournament flows | `game/tournaments` | tournament models, lifecycle/messaging/proof workers |
| Daily Cup | bot Daily Cup flows | tournaments and session Daily Cup modules | seven beat flows, messaging/proof/result workers |
| Purchases/Stars | payments handlers, webhook | `economy/purchases` | purchases, ledger, entitlements, reliability workers |
| Promo/referrals/offers | bot/admin handlers | economy services | promo/referral tables, maintenance and observability tasks |
| Admin/analytics | FastAPI admin/ops | admin services and route helpers | three independent metrics pipelines |
| Telegram reliability | webhook and delivery services | workers/task-specific adapters | processed updates, delivery attempts, mixed outbox ledger |

Feature ownership is distributed. Domain mutations are generally centralized,
but transaction ownership, broker enqueue, rendering, and delivery policy often
remain in handlers and workers.

## 6. Entrypoints and composition

- `app/main.py:22-66` creates FastAPI, routers, middleware, and static mount;
  `app = create_app()` executes at import.
- `app/db/session.py:25-36` creates engine and `SessionLocal` at import.
- `app/workers/celery_app.py:7-42` creates the global Celery app and imports
  task modules that register schedules.
- `app/bot/application.py:17-43` caches a process-global Dispatcher;
  `build_bot` also installs a global diagnostics patch.
- `scripts/run_bot_polling.py` calls `start_polling`; it has no explicit
  `delete_webhook`.
- FastAPI `lifespan`/startup/shutdown hooks were not found; the API does not
  invoke the available `dispose_engine`.
- Settings, Redis clients, admin caches, Dispatcher, and some gameplay cooldown
  state have process-global lifecycles.

## 7. Framework leakage

Static signals:

- 17 bot files directly import DB session; 11 import repositories.
- 25 API files use `SessionLocal`; 14 import repositories; 26 import ORM
  models; 3 import worker modules.
- 40 worker files directly use models/repositories.
- 121 modules in `game/economy/services` import SQLAlchemy, aiogram, or FastAPI.
- `workers → bot` has 39 import edges; workers construct `Bot` and use bot
  texts/keyboards.
- Repositories do not import bot or workers.
- The narrow prohibition `core/db/economy/game/services → app.bot` holds, but
  it does not cover actual `game → workers → bot` and `bot ↔ workers` paths.

Persistence does not leak downward from repositories, but presentation,
application, and worker boundaries are not isolated.

## 8. Persistence and transaction ownership

- `125` `SessionLocal.begin()` calls are distributed across API 44, bot 20,
  services/economy 3, and workers 58.
- No explicit production `.commit()`/`.rollback()` was found; context managers
  own commit/rollback.
- `49` `flush()` calls occur in 37 files.
- `64` `FOR UPDATE` calls occur in 28 files; 63 are in repository code.
- Repository-level commit was not found; this is a confirmed positive boundary.
- A lexical AST scan found 20 transaction blocks with Telegram I/O before
  leaving the context manager. Manually confirmed examples include answer error
  responses, Arena notification, Daily Cup walkover, and multiple lobby/share
  flows.
- ORM contains 42 tables; the migration graph is linear with 60 revisions and
  one head.
- Ledger append-only behavior is protected by ORM hooks and a DB trigger.

The critical exception is that several `IntegrityError` recovery branches query
through the same session after a failed `flush`, without savepoint or rollback.

## 9. Messaging, outbox, and retry architecture

Central Telegram delivery:

1. Create or claim a `PENDING` attempt and commit it.
2. Send the Telegram message outside the transaction.
3. Mark `SENT` in a second transaction.

Terminal replay for `SENT/SKIPPED/FAILED` suppresses another send.
`TelegramRetryAfter` remains `PENDING`; known forbidden/bad-request errors
become `FAILED`. An unclassified exception leaves the row nonterminal and is
re-raised.

Retry/blocked repositories exist, but no production consumer, schedule, or
admin reader was found. Reusable repair primitives therefore exist without a
confirmed generic repair loop.

`outbox_events` is not a dispatcher-outbox. Its repository supports
create/read/count/delete but not claim/publish/status transitions. The table
mixes `OPEN`, `SENT`, and `FAILED` audit/review semantics.

Inbound updates have `PROCESSING/PROCESSED/FAILED`, retries, and stale reclaim,
but no heartbeat. Fresh `PROCESSING` redelivery is treated as duplicate-success;
scheduled observability only alerts and does not re-enqueue.

## 10. Workers and schedules

Global Celery settings: JSON serialization, Europe/Berlin, UTC enabled,
`acks_late=True`, prefetch `1`, default `q_normal`. The worker listens on
`q_high,q_normal,q_low`.

All 32 beat entries:

- Admin/analytics:
  - `admin-daily-metrics` hourly, `q_low`.
  - `analytics-daily` hourly, `q_low`.
- Gameplay:
  - Arena expiry every 5 minutes.
  - Question-set precompute at 00:00, `q_low`.
  - Daily push at 08:00, `q_low`.
  - Evening push at 19:00, `q_low`.
- Daily Cup:
  - Registration at 16:00.
  - Last call at 16:30.
  - Prestart at 16:50.
  - Turn reminders every 10 minutes.
  - Close at 17:00.
  - Final results at 20:05.
  - Round advance every minute.
  - All Daily Cup schedules use `q_normal`.
- Friend/tournaments:
  - Friend deadlines every 5 minutes.
  - Private tournament lifecycle every 5 minutes.
- Offers:
  - Funnel alerts every 15 minutes.
- Payments:
  - Recover paid-uncredited every 5 minutes, `q_high`.
  - Invariant alerts every minute, `q_high`.
  - Expire invoices every 5 minutes.
  - Refund/promo rollback every 5 minutes.
  - Reconciliation every 15 minutes.
  - Reconciliation daily at 03:30.
  - Stars reconciliation every 5 minutes.
- Promo:
  - Reservation expiry every minute.
  - Campaign rollover every 10 minutes.
  - Bruteforce guard every minute.
- Referrals:
  - Qualification every 10 minutes.
  - Reward distribution every 15 minutes.
  - Reward distribution monthly at day 1, 00:05.
  - Fraud alerts every 15 minutes.
- Retention:
  - Hourly or configured 03:15, `q_low`.
- Telegram:
  - Update-reliability alerts every 5 minutes.

Global hard/soft Celery time limits, per-task heartbeat, and worker/beat
container healthchecks were not found. Most scheduled entrypoints do not have
task-level retry; retries exist only in selected inbound/delivery flows.

## 11. Payments and entitlement architecture

The main successful-payment path has two durable checkpoints:

1. A successful-payment transaction moves the purchase to `PAID_UNCREDITED`.
2. A subsequent transaction credits assets, ledger, entitlement/promo state,
   and changes the purchase to its credited state.

This lets scheduled recovery find paid-but-uncredited purchases. Credit uses row
locks and idempotency keys; premium has a partial unique active-row invariant.

Stars reconciliation retrieves provider transactions before opening DB recovery
transactions. Exact recovery locks purchase, charge evidence, ledger, and
entitlement and atomically writes credit plus an audit event.

Material gaps:

- Payment evidence lifecycle columns never advance from `RECEIVED`.
- Purchase-init race recovery uses an aborted transaction.
- Catalog saleability for a soft-disabled product is checked in the bot handler,
  not the domain service.
- Refund ledger records a full reversal even when already-consumed energy/saver
  can only be clawed back partially.
- `payments_reliability_async.py` has 792 lines and combines provider I/O,
  recovery policy, transactions, manual review, audit, and alerts.

## 12. Gameplay architecture

Regular start:

```text
handler transaction
  → onboarding
  → mode policy
  → energy lock/debit
  → question selection
  → QuizSession insert
  → commit
  → render/send
```

Energy debit and session creation are atomic; a later error rolls back the debit.

Answer:

```text
lock QuizSession
  → create attempt
  → complete session
  → Daily/Friend/Streak/progression updates
  → commit
  → post-commit rendering/follow-ups
```

Daily:

- DB guarantees one `COMPLETED` run per user/date.
- One active `DailyRun` is not guaranteed.
- One started Daily `QuizSession` has partial unique protection.

Arena/private tournament domain transitions generally use row or advisory locks.
The main weaknesses are post-commit delivery/replay and enqueue ordering rather
than missing locking in state mutation.

Gameplay selects questions from the local database. A runtime HTTP client to the
separate QuizBank service was not found in `app/**`.

## 13. Analytics and admin architecture

Admin:

- Runtime roles are `admin` and `super_admin`; no separate `owner` role exists.
- 31 admin domain endpoints check verified 2FA.
- Redis-backed token revocation, TOTP, and admin rate limiting fail closed with
  `503`.
- Promo raw-code reveal is separately protected by `super_admin`.

Metrics have three independent pipelines:

1. `admin_daily_metrics` writes `daily_metrics`.
2. `analytics_daily` writes `analytics_daily`.
3. `/admin/overview` uses live queries and Redis cache.

A production reader for `daily_metrics` was not found. Active-user definitions
differ between the worker aggregation and live overview.

`/admin/system` treats Redis list `celery` as a failed queue even though the
default queue is `q_normal` and no `celery` DLQ is configured. Its webhook
health depends on recent traffic rather than an independent readiness probe.

## 14. External integration boundaries

- Telegram webhook: shared-secret header, payment evidence, Celery enqueue.
- Telegram Bot API: central delivery service plus multiple task-specific raw
  send paths.
- Telegram Stars API: reconciliation worker; default reconciliation is
  disabled/dry-run by configuration.
- PostgreSQL: authoritative gameplay/economy state.
- Redis: Celery broker/results, FSM, admin revocation/TOTP/rate-limit/cache, and
  ops sessions.
- Ops alerts: best-effort HTTP with a 5-second timeout and no durable retry.
- QuizBank: Caddy proxy to a separate container/repository; no backend runtime
  client was found.
- Frontend: standalone image/repository outside this snapshot.

## 15. Test and quality-gate map

Static test signals are strong for purchase credit/refund/reconciliation, ledger
append-only behavior, Daily flow, friend/Arena/tournaments, promo concurrency,
referrals, and messaging.

Structural hotspots:

- `tests/workers/test_telegram_stars_reconciliation_task.py`: 1,232 lines and
  76 `monkeypatch` calls.
- `tests/services/test_telegram_delivery.py`: 465 lines.
- `tests/game/test_sessions_start_arena.py`: 403 lines.
- 11 tests inspect source text or paths rather than behavior only.

Read-only gate results:

| Gate | Result |
|---|---|
| `check_architecture_imports.sh` | Passed |
| `check_import_cycles.sh` | Passed after running its Python logic through the available Windows Python; the standard launcher initially could not find `python3` |
| `check_no_print_app.sh` | Passed |
| `check_no_except_exception_pass.sh` | Passed |
| `check_line_limits.sh` | Passed with 31 warnings for `app` files over 200 lines |
| `check_architecture_debt.py` | Exit 0, but the local result is invalid because of a Windows path-separator bug |
| `make lint` | Did not start: `make` unavailable |
| `make format-check` | Did not start: `make` unavailable |
| `make type-check` | Did not start: `make` unavailable |
| Tests | Not run |

The Ubuntu CI workflow has `lint_unit → integration → tournament_regression`,
but the current GitHub CI run was not inspected.

## 16. Architecture guard blind spots

- `scripts/check_architecture_imports.sh:7-18` sees only direct textual
  `app.bot` imports in five directories; it does not see `workers ↔ bot`,
  `game ↔ workers`, or relative/local/dynamic imports.
- `scripts/check_import_cycles.sh:69` analyzes only `tree.body`; lines 142-146
  exclude `__init__.py`.
- `check_monolith_pattern.sh` counts only column-zero `def`/`if`, misses async
  methods/classes, and always exits `0`.
- `check_no_print_app.sh` uses the literal regex `\bprint\(`.
- `check_no_except_exception_pass.sh` sees single-line
  `except Exception: pass`, not the normal multiline block.
- Line/debt/growth guards compare `origin/main...HEAD`; current legacy debt is
  warning-only. Growth guard skips outside CI.
- `scripts/check_architecture_debt.py:161` stores Windows paths through
  `str(path)`, while line 186 checks `startswith("app/")`; all 1,384 candidate
  paths therefore bypass local policy classification.
- Guards do not measure class responsibility, framework leakage,
  transaction/network ordering, or delivery state machines.

## 17. Documentation drift

- `.agent/project/TECH_DEBT_REMEDIATION_PLAN.md:72-75` reports 29 app files over
  200 lines and 84 functions over 60 lines; the live scan gives 31 and 85.
  Counts for excessive parameters (`74`), nesting (`13`), and the four primary
  hotspots still match.
- `docs/architecture/current_runtime_map.md:44-81` omits the mandatory
  payment-evidence transaction before webhook enqueue.
- Its rule that bot handlers only orchestrate is only partly true because of
  direct DB/query/task ownership.
- `docs/analytics/events_catalog.md:179,195-200` still describes
  `telegram_payment_update_received` in outbox “until dedicated inbox exists”;
  the dedicated inbox exists and a current producer of the old event type was
  not found.
- `current_runtime_map` does not describe the separate `daily_metrics` writer
  pipeline.
- `IMPLEMENTATION_ARCHITECTURE.md` and
  `docs/architecture/technical_debt_baseline.md` are explicitly historical;
  their old paths and counts are not treated as active contradictions.
- The narrow Phase-1 admin Redis fail-closed claim is confirmed, but the
  historical test result was not rerun and does not cover the new auth findings.

## 18. Concrete findings registry

Confidence labels:

- `Confirmed`: direct code or code-and-test evidence.
- `High inference`: the consequence follows reliably from ordering/state.
- `Tentative`: runtime/data applicability still requires proof.

### AR-001 — High — Security — TOTP secret disclosure

Fact: `app/api/routes/admin/auth.py:111-120` allows `/2fa/setup` for
`get_pending_admin`, while `app/services/admin/auth_totp.py:10-23` returns an
already existing secret.

Conclusion: a password-only partial token can read the current second-factor
secret. A service test confirms reuse; a negative API test for an unverified
principal is absent.

Confidence: `Confirmed`.

### AR-002 — High — Security — Refresh replay

Fact: `app/api/routes/admin/auth_session.py:14-41` issues a new token pair
without revoking the predecessor, and
`app/services/admin/auth_tokens.py:33-44` has no `jti`.

Conclusion: the old refresh token remains replayable until expiry.
Rotation/replay coverage was not found.

Confidence: `Confirmed`.

### AR-003 — High — Security — Partial logout revocation

Fact: `app/api/routes/admin/auth_session.py:44-63` revokes access and refresh
sequentially in one `try`. Failure of the first operation skips the second while
cookies are still cleared. The API test explicitly expects refresh revocation
not to run after access-revocation failure.

Conclusion: a copied refresh token may remain valid after the state store
recovers.

Confidence: `Confirmed`.

### AR-004 — High — Security/identity — Stale claims remain authoritative

Fact: refresh does not compare email/role with current configuration.
`get_pending_admin` passes token claims to `AdminsRepo.get_or_create`, which can
rewrite the DB role.

Conclusion: an old valid refresh token can restore stale identity/role claims.

Confidence: `Confirmed code path`; production exploit not tested.

### AR-005 — Medium — Security — Process-local Ops throttle

Fact: `app/api/routes/ops_ui/state.py:6-7` stores counters in a dict protected by
a thread lock. Production API runs four Uvicorn workers.

Conclusion: limits are independent between workers and reset on restart.

Coverage: tests are single-process.

Confidence: `Confirmed`.

### AR-006 — High — Dependency boundary — Hidden `bot ↔ workers` cycle

Fact:

1. `app/bot/handlers/gameplay_proof_cards.py:9` locally imports the friend proof
   worker.
2. The worker top-level imports `app.bot.application.build_bot`.
3. Bot application imports the gameplay router.
4. Gameplay imports `gameplay_proof_cards`.

Conclusion: this is a real architectural cycle, although not a proven
import-time crash because one edge is deferred inside a function. The official
cycle guard cannot see it.

Confidence: `Confirmed`.

### AR-007 — High — Transaction/boundary ownership

Fact: bot, API, and workers directly own `SessionLocal.begin`, repositories,
models, enqueue, and send. A lexical AST scan found 20 transaction blocks with
Telegram I/O before transaction exit; concrete cases were manually confirmed.

Conclusion: network latency can extend locks and send/commit outcomes can become
ambiguous.

Confidence: `Confirmed pattern`.

### AR-008 — High — Persistence — Recovery after failed flush

Fact: `app/game/sessions/service/sessions_start_daily.py:75-96,145-174` and
`app/economy/purchases/service/init.py:101-122` catch `IntegrityError` and
immediately query through the same session without savepoint or rollback.

Conclusion: intended loser-side recovery cannot operate in PostgreSQL's aborted
transaction state.

Coverage: the purchase unit test mocks the session and does not reproduce real
PostgreSQL behavior; Daily concurrency integration was not found.

Confidence: fact `Confirmed`, runtime consequence `High inference`.

### AR-009 — High — Concurrency — Multiple active Daily runs

Fact: `app/db/models/daily_runs.py:42-48` enforces uniqueness only for
`COMPLETED`. Creation is check-then-insert, and the repository chooses one
ordered row if several exist.

Conclusion: the `daily_runs` table does not enforce one current in-progress run.
The full public start also has a partial unique started-QuizSession constraint,
so a persistent duplicate from the complete flow was not reproduced.

Confidence: invariant gap `Confirmed`; runtime incidence `Tentative`.

### AR-010 — Medium — Concurrency — Friend caps checked before lock

Fact: active/daily cap guards execute before the per-user access serialization
lock.

Conclusion: concurrent creates can both pass cap checks.

Coverage: a concurrent cap integration test was not found.

Confidence: `High inference`.

### AR-011 — High — Gameplay delivery — Arena result cannot be replayed

Fact: terminal Arena completion is committed before post-commit rendering.
`app/game/arena_duels/service_challenger_complete.py:82-85` returns an
already-completed replay without terminal result data, and the renderer returns
without a result view. A test codifies this empty replay.

Conclusion: a post-commit delivery failure cannot be recovered through normal
update replay.

Confidence: `Confirmed`.

### AR-012 — High — Gameplay delivery — Arena notification inside transaction

Fact: Arena notification keeps a DB transaction and advisory lock open during
Telegram send. The gameplay path invokes the async function directly and
ignores its failure count even though a Celery entrypoint exists.

Conclusion: send-success/commit-failure can duplicate, while direct send failure
has no task retry.

Confidence: `High inference`.

### AR-013 — High — Economy/messaging — Revanche marked before send

Fact: `arena_revanche_delivery.py:106-134` commits challenge/sent state before
network delivery. Generic ambiguous failure has no cleanup. Ticket usage partly
derives from an analytics event. A test confirms committed sent state without a
message.

Conclusion: delivery state can diverge from provider delivery, and analytics
becomes authoritative economy input.

Confidence: `Confirmed`.

### AR-014 — High — Messaging — Friend quota consumed before send

Fact: friend push quota is committed before Telegram delivery, and generic send
exceptions are swallowed.

Conclusion: a failed delivery permanently consumes quota.

Confidence: `Confirmed`.

### AR-015 — High — Messaging — Deadline marker before best-effort send

Fact: Friend Challenge deadline decisions set a notification marker before a
raw Telegram send; exception becomes a count. There is no durable attempt/retry
state for this channel.

Conclusion: failed deadline delivery is durably recorded as notified.

Confidence: `Confirmed`.

### AR-016 — High — Broker boundary — Proof-card enqueue gaps

Fact: friend/private tournament completion commits before enqueue. Broker
exceptions are swallowed or returned as a result that callers may ignore.
Replay guards normally do not enqueue again.

Conclusion: commit-success/enqueue-failure can permanently lose proof delivery.

Confidence: `Confirmed`.

### AR-017 — High — Daily Cup — Pre-commit enqueue and in-transaction send

Fact: `app/game/tournaments/lifecycle.py:124-145` can enqueue next-round work
before the caller commits. Walkover follow-up sends Telegram messages inside the
state transaction. Broker/send failures are swallowed.

Conclusion: workers can race uncommitted state, broker failure can lose work,
and network latency extends locks.

Confidence: `Confirmed`.

### AR-018 — High — Telegram delivery — Orphan repair infrastructure

Fact: unclassified delivery exceptions leave `PENDING`; retry-claim and
blocked-candidate repositories exist, but no production consumer, schedule, or
admin reader was found.

Conclusion: reusable repair primitives do not form a production repair loop.

Coverage: repository/service primitives are tested; end-to-end repair is not.

Confidence: `Confirmed`.

### AR-019 — High — Telegram delivery — Send/mark crash window

Fact: `app/services/telegram_delivery.py:29-72` commits `PENDING`, sends, then
commits `SENT` separately.

Conclusion: a crash after provider success but before `SENT` leaves an unknown
`PENDING`; stale replay can send a duplicate.

Confidence: `High inference`.

### AR-020 — High — Daily push — Sent log precedes send

Fact: `daily_challenge_async.py:91-118` creates the sent log before
`bot.send_message`; exception only increments skipped. The test codifies this
behavior.

Conclusion: an unsent push becomes durably ineligible for retry.

Confidence: `Confirmed`.

### AR-021 — High — Daily Cup batch messaging

Fact: raw sends/edits run as a batch; message IDs are persisted only after the
whole batch returns.

Conclusion: a mid-batch crash leaves partial delivery without matching DB state
and may duplicate early sends on replay.

Coverage: no partial-batch crash recovery test was identified.

Confidence: `High inference`.

### AR-022 — High — Inbound update lease — No heartbeat or repair trigger

Fact: fresh `PROCESSING` redelivery is treated as duplicate-success; stale
reclaim is age-only; observability does not re-enqueue.

Conclusion: worker loss before TTL can leave an update without another trigger,
while a long handler surviving past TTL can be reclaimed concurrently.

Confidence: `High inference`.

### AR-023 — High — Referrals — Notified before delivery

Fact: the reward worker commits `notified_at` and then sends. Failed rows are not
selected again.

Conclusion: failed reward-ready messages are permanently considered notified.

Coverage: successful once-only delivery is tested; failure recovery is not.

Confidence: `Confirmed`.

### AR-024 — Medium — Payments evidence — Lifecycle fields unused

Fact: `TelegramUpdateInbox` and `PaymentEvent` contain processed/failure fields,
but production repositories only create/get rows. The processing worker updates
the separate `ProcessedUpdate` mechanism.

Conclusion: payment evidence remains `RECEIVED` regardless of whether the
payment update was applied or failed.

Confidence: `Confirmed`.

### AR-025 — Medium — Domain invariant — Catalog saleability in UI

Fact: purchase service accepts a catalog product without checking saleability.
Soft-disabled `PREMIUM_3_DAYS` is rejected by the bot handler.

Conclusion: saleability is a presentation rule, not a purchase-domain
invariant. No exploitable alternate production entrypoint was established.

Confidence: boundary gap `Confirmed`.

### AR-026 — Medium — Promo semantics — First purchase counts every row

Fact: promo eligibility counts all purchase rows without payment-status filter.
CREATED/failed invoices and internal zero-cost reward purchases are included.

Conclusion: `new_users_only`/`first_purchase_only` can be blocked without a
prior paid purchase.

Coverage: CREATED purchase behavior is tested; the Daily reward cross-context
case is not.

Confidence: `Confirmed`.

### AR-027 — Medium — Refund semantics — Full reversal, partial clawback

Fact: refund removes only energy/saver still present but records the full ledger
reversal and changes purchase state to `REFUNDED`.

Conclusion: ledger symmetry proves payment reversal, not recovery of already
consumed gameplay benefits. This may be intentional policy, but no separate
unrecovered-benefit model exists.

Confidence: fact `Confirmed`; product risk unverified.

### AR-028 — Medium — Outbox semantics — No dispatcher state machine

Fact: `app/db/repo/outbox_events_repo.py:45-226` has no
claim/publish/resolve transition. `OPEN/SENT/FAILED` are audit/manual-review
labels.

Conclusion: the name “outbox” implies a stronger delivery contract than the
actual implementation.

Confidence: `Confirmed`.

### AR-029 — Medium — Worker reliability — No global limits or health

Fact: `app/workers/celery_app.py:32-41` defines no hard/soft task limits;
heartbeat is absent; worker and beat containers have no healthcheck. Retention
has only an application-level budget.

Conclusion: stuck/long-running task detection is not enforced by the global
worker contract.

Confidence: `Confirmed`.

### AR-030 — Medium — Analytics — Divergent/orphan metrics pipelines

Fact: hourly `daily_metrics`, hourly `analytics_daily`, and live overview use
different active-user definitions. A production reader for `daily_metrics` was
not found.

Conclusion: admin metrics can disagree and one persisted pipeline has no
identified runtime consumer.

Confidence: `Confirmed`.

### AR-031 — Medium — Admin observability — Queue/health semantics

Fact: `admin/system.py:118-125` calls Redis list `celery` failed queue without a
configured DLQ; webhook health depends on recent traffic. A test codifies the
queue mapping.

Conclusion: the dashboard can report a misleading failed count or unhealthy
webhook during a legitimate low-traffic interval.

Confidence: queue behavior `Confirmed`; operational interpretation `Tentative`.

### AR-032 — Medium — Runtime state — Process-global lifecycle

Fact: app, engine, settings, Dispatcher, Redis clients, throttles, and cooldowns
are created/cached at process scope. API cleanup hooks were not found.

Conclusion: semantics depend on multiprocess topology and restart lifecycle.
An actual resource leak at process exit was not proven.

Confidence: structure `Confirmed`.

### AR-033 — Medium — Daily Cup UI — Unbounded local cooldown map

Fact: `daily_cup_menu_flow.py:16-25` stores user IDs without pruning and does
not share state across Celery child processes.

Conclusion: cooldown enforcement differs per process and memory grows with
unique users until restart.

Confidence: `Confirmed`.

### AR-034 — Medium — Responsibility concentration

Fact:

- 31 production files exceed 200 lines.
- 85 functions exceed 60 lines.
- 74 functions exceed 7 parameters.
- 13 functions exceed nesting depth 3.
- `payments_reliability_async.py` has 792 lines and combines provider I/O,
  recovery policy, transactions, review, audit, and alerts.

Conclusion: change/review/test cost is concentrated in orchestration hotspots.

Confidence: `Confirmed`.

### AR-035 — Medium — Test maintainability

Fact: the 1,232-line reconciliation test has 76 monkeypatch calls, and two more
tests exceed 400 lines. Critical aborted-transaction, concurrent Daily/friend
caps, and delivery crash windows lack identified integration coverage.

Conclusion: tests reveal high coupling while leaving several failure-ordering
paths unexercised.

Confidence: `Confirmed static inventory`.

### AR-036 — Medium — Guard coverage

Fact: cycle/import/monolith/debt guards do not see local/package cycles,
semantic responsibility, framework leakage, or transaction-delivery ordering.
The Windows debt run produces a vacuous pass.

Conclusion: passing guards is not evidence that architectural boundaries or
delivery state machines are healthy.

Confidence: `Confirmed`.

### AR-037 — Low — Documentation drift

Fact: active debt counts, webhook flow, and payment evidence/outbox catalog do
not match current code. Historical documents correctly self-identify as
historical.

Conclusion: active operational documentation is partially stale/incomplete.

Confidence: `Confirmed`.

### AR-038 — Low/Medium — Duplicate orchestration

Fact: Friend-create has both a wired lobby implementation and a separate
directly tested create implementation. `_acquire_processing_slot` is also
duplicated in two worker modules.

Conclusion: parallel policy surfaces can drift.

Confidence: `Confirmed`.

### AR-039 — Low — Configuration drift

Fact: Daily Cup share text hardcodes `Deine_Deutsch_Quiz_bot` while the base link
is configurable.

Conclusion: changing the configured bot link can leave user-facing share text
stale.

Confidence: `Confirmed`.

### AR-040 — Medium — Tentative concurrency — First-row creation

Fact: energy/streak default rows use check-then-insert without conflict
recovery. Onboarding reduces normal applicability for energy.

Conclusion: legacy/missing rows and concurrent first streak access can raise
`IntegrityError`.

Confidence: `Tentative`.

## 19. Confirmed clean areas

- Research snapshot and working tree were clean.
- The top-level non-package import graph has zero SCC.
- Repositories do not commit and do not depend on bot/workers.
- Admin access/refresh decode, TOTP state, and rate limits fail closed on Redis
  outage.
- Webhook payment evidence is durable before enqueue and does not store raw
  headers/secrets.
- Purchase credit has a recoverable `PAID_UNCREDITED` checkpoint.
- Energy debit and session creation are atomic.
- Purchase credit, entitlement extension, and Arena/tournament transitions use
  locks and idempotency keys extensively.
- Ledger append-only behavior is protected at application and DB layers.
- Alembic has one head.
- All 153 statically addressed `TEXTS_DE[...]` keys exist.
- Private tournament standings delivery has a stronger
  advisory-lock/CAS/retry flow with race-oriented tests.
- Caddy blocks public `/ready` and exposes sanitized `/health`.
- Backend gameplay does not mix an external QuizBank runtime client with local
  question selection.

## 20. Unverified areas

- Complete test suite, Ruff, Black, isort, mypy, and current GitHub CI results.
- Live PostgreSQL schema/data and the actually applied migration head.
- Production SHA, environment, queue depths, Redis/Postgres state, and incident
  history.
- `.env` contents and real secret distribution.
- Telegram/Celery failure windows in runtime.
- Standalone frontend and QuizBank implementation/API contract.
- Polling behavior while a webhook is active.
- Dynamic imports, runtime-generated presentation strings, and DB content.
- Any external/manual process that may resolve `OPEN outbox_events`.
- Actual duplicate Daily runs, concurrent cap violations, or lost notifications
  in production.

## 21. Inputs required for a future design phase

Without entering solution design, a future design phase requires:

- Explicit delivery semantics for every notification class: acceptable
  duplicates, loss, and retry window.
- Admin policy for TOTP enrollment/recovery, refresh rotation, role/email
  invalidation, and logout guarantees.
- Confirmed production topology: worker concurrency, queue ownership, restart,
  and timeout policy.
- Product semantics for friend quotas, tickets, promo “first purchase”, and
  refunds of consumed benefits.
- Live schema/migration snapshot and anonymized invariant counts.
- Incident/telemetry evidence for stuck `PROCESSING/PENDING`,
  paid-uncredited, and notification failures.
- Current CI artifacts and coverage report.
- Versioned frontend/QuizBank contract and deployment ownership.
- An authoritative definition for admin DAU/WAU/MAU and queue health.

## 22. What was not changed during research

- No tracked or untracked project file was changed during the audit itself.
- No commit, branch, PR, stash, merge, rebase, reset, or cherry-pick was created
  during the research phase.
- Tests, build, deploy, and production commands were not run.
- `.env` was not read.
- External repositories were not inspected.
- The research ended on `main` with `HEAD == origin/main` and a clean working
  tree.
