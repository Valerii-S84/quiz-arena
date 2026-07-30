# Quiz Arena — Target Modular Clean Architecture Decision

**Status:** Accepted design baseline  
**Decision type:** Target architecture and incremental migration strategy  
**Repository baseline:** `main` at `e4c1e6721f60c746cb3c3666fb03264859af71cc`  
**Research date:** 2026-07-30  
**Scope:** Quiz Arena backend: FastAPI, aiogram, Celery, PostgreSQL, Redis, Telegram integrations, admin and analytics  

---

## 1. Decision summary

Quiz Arena remains a **modular monolith**. The system will be migrated incrementally toward a pragmatic Clean Architecture:

```text
Domain → Application → Adapters / Infrastructure
```

The migration will not be a rewrite, will not introduce microservices, and will not create empty architectural layers across the whole repository in advance.

The decisive rules are:

1. **Business rules live in modules, not in Telegram handlers, FastAPI routes or Celery tasks.**
2. **Application use cases own transaction boundaries.**
3. **No Telegram, broker or other network I/O occurs inside a database transaction.**
4. **A module never imports another module's adapters, repositories or ORM models.**
5. **A normal use case uses a module-scoped Unit of Work.**
6. **A rare cross-module operation that must be atomic is implemented as an explicit, bounded application workflow with one database transaction.**
7. **A non-atomic cross-module operation uses a durable integration event persisted in PostgreSQL.**
8. **Domain events are synchronous and internal to one module; they are not a transport mechanism between modules.**
9. **Critical Telegram delivery is at-least-once, not exactly-once. Duplicate business mutations are forbidden; a duplicate message in the unavoidable provider crash window is tolerated and observed.**
10. **The first production dispatcher runs through the existing Celery deployment on a dedicated `q_delivery` queue; no fifth long-running process is introduced initially.**
11. **Manual replay reuses the same outgoing row and the same idempotency key; replay never clones the business effect.**
12. **Architecture migration starts with a low-risk, single-module pilot, not Arena.**
13. **Definition of Done is scaled by slice risk; low-risk pilots do not carry payment-grade ceremony.**
14. **`app/workflows/` is an exception boundary with hard limits, not a general orchestration package.**
15. **Known security vulnerabilities are release blockers and are fixed before architecture migration.**
16. **Admin visibility for failed and stuck asynchronous work ships together with the corresponding dispatcher, not later.**
17. **Every temporary legacy/new pair is registered, time-bounded and automatically checked; at most two dual-path migrations may be active at once.**
18. **Every slice is independently valuable and pausable; the roadmap is not an all-or-nothing commitment.**

The first architecture pilot is **promo reservation expiry**. Arena migration begins only after the transaction, port, testing and cutover patterns have been proven on simpler flows.

---

## 2. Context

The current system contains substantial and valuable production logic:

- strong PostgreSQL invariants in purchases, ledger, entitlements and gameplay;
- broad use of row locks, advisory locks and idempotency keys;
- atomic energy debit and quiz-session creation;
- a durable `PAID_UNCREDITED` checkpoint for purchase recovery;
- repositories that do not commit transactions;
- a linear Alembic migration graph with one head;
- significant automated test coverage around payments, gameplay and competitions.

The design must preserve those strengths.

The primary architectural risk is not an absence of business logic or database protection. It is the placement of orchestration and external effects:

- FastAPI routes, bot handlers and Celery workers open transactions directly;
- presentation code imports persistence details;
- workers import bot texts, keyboards and bot construction;
- `bot → workers → bot` and related hidden dependency cycles exist;
- Telegram sends and Celery enqueue operations occur before commit or inside open transactions;
- some state changes are committed before best-effort delivery and become unrecoverable;
- retry primitives exist without a complete dispatcher, lease and operator-visibility protocol;
- process-local state behaves incorrectly under four API workers and Celery child processes;
- three analytics pipelines use divergent definitions;
- current architecture guards can return false passes.

Therefore the target is not “more folders.” The target is reliable ownership of:

- business policy;
- transactions;
- external effects;
- cross-module coordination;
- retry and replay;
- dependency direction.

---

## 3. Goals

### 3.1 Primary goals

- Make business use cases testable without FastAPI, aiogram, Celery, Redis or the Telegram Bot API.
- Give every mutation flow one explicit transaction owner.
- Remove external network I/O from database transactions.
- Eliminate dependency cycles between delivery, workers and business modules.
- Preserve existing database invariants and idempotency behavior.
- Make critical asynchronous work recoverable and operationally visible.
- Allow gradual migration while the production bot remains live.
- Keep the design understandable and maintainable for a solo developer.

### 3.2 Success criterion

For every migrated use case, it must be possible to state clearly:

```text
Who accepts the request?
Who owns the transaction?
Which module owns each business rule?
Which state is committed atomically?
Which external effects are durable?
What happens after every relevant crash point?
How is the new path enabled and rolled back?
```

If any answer is implicit, distributed across handlers and workers, or depends on call order by convention, the slice is not complete.

---

## 4. Non-goals

This decision does **not** authorize:

- a rewrite of the entire repository;
- migration to microservices;
- a new generic dependency-injection framework;
- separate domain classes for every ORM model regardless of value;
- an interface for every class or function;
- a universal enterprise event bus;
- a repository per database table;
- replacing SQLAlchemy, Celery, FastAPI or aiogram;
- moving code only to satisfy folder aesthetics;
- changing working business behavior without characterization tests;
- claiming exactly-once delivery to Telegram;
- creating empty `domain/application/adapters` directories for all future modules before a real slice needs them.

The design optimizes for **clear boundaries and reliable behavior**, not maximal architectural ceremony.

---

## 5. Target system shape

### 5.1 Logical layers

```text
External request or scheduled trigger
                │
                ▼
            Entrypoint
    FastAPI / aiogram / Celery / CLI
                │
                ▼
        Application use case
    commands, queries, workflows, ports
                │
                ▼
              Domain
     rules, state transitions, policies
                │
                ▼
       Adapter implementations
 SQLAlchemy / Redis / Telegram / broker
                │
                ▼
         Infrastructure runtime
 engines, clients, configuration, lifecycle
```

Dependencies point inward. Infrastructure implements ports defined by the application or owning module. Domain code does not know which framework executes it.

### 5.2 Initial business modules

The target logical modules are:

| Module | Owns |
|---|---|
| `gameplay` | regular quiz, Daily Quiz, sessions, attempts, questions, energy, streak and progression |
| `competitions` | friend challenges, Arena, private tournaments and Daily Cup |
| `economy` | catalog, purchases, Stars, entitlements, ledger, promo, referrals, offers and refunds |
| `admin_identity` | admin login, roles, TOTP, refresh sessions, token revocation and security policy |
| `messaging` | durable outgoing delivery, incoming processing leases, retries and delivery status |
| `analytics` | authoritative metric definitions, aggregation and admin reporting contracts |

These are ownership boundaries, not mandatory immediate directories. A module is created or migrated only when an actual vertical slice requires it.

### 5.3 Supporting areas

```text
app/
├── modules/           # migrated business modules
├── workflows/         # explicit cross-module atomic workflows
├── entrypoints/       # HTTP, Telegram, Celery and CLI adapters
├── infrastructure/    # runtime clients and concrete framework setup
├── bootstrap/         # composition roots
└── legacy/            # optional temporary namespace only when useful
```

The existing `app/bot`, `app/api`, `app/game`, `app/economy`, `app/workers`, `app/services` and `app/db` packages remain during migration. They are reduced slice by slice rather than moved wholesale.

---

## 6. Dependency rules

### 6.1 Domain

Domain code may import:

- Python standard library;
- domain types from the same module;
- small shared value types that have no framework dependency.

Domain code must not import:

- SQLAlchemy;
- FastAPI;
- aiogram;
- Celery;
- Redis clients;
- application configuration;
- ORM models;
- another module's adapters or repositories.

### 6.2 Application

Application code may import:

- its own domain;
- its own port protocols;
- immutable DTOs and command/query types;
- explicitly permitted public contracts of another module;
- workflow-local ports for cross-module atomic operations.

Application code must not import:

- aiogram objects;
- FastAPI request/response objects;
- Celery task decorators;
- `SessionLocal`;
- concrete SQLAlchemy repositories;
- Telegram bot clients;
- another module's adapter package.

### 6.3 Adapters

Adapters may import frameworks and implement ports. Examples:

- SQLAlchemy repository adapter;
- Redis rate-limit adapter;
- Telegram delivery adapter;
- Celery task entrypoint;
- FastAPI route entrypoint;
- aiogram presenter.

An adapter may depend on the application contract it implements. Business modules must not depend back on the adapter.

### 6.4 Module boundaries

A module may consume another module through only one of these mechanisms:

1. a stable public application contract;
2. an explicit cross-module workflow port;
3. a durable integration event;
4. a read-only published query contract.

A module must never import another module's:

- ORM models;
- SQLAlchemy repositories;
- adapter implementations;
- private application services;
- Telegram presenters;
- Celery tasks.

---

## 7. Transaction ownership

### 7.1 General rule

Every mutation has exactly one application-level transaction owner.

Entrypoints do not open transactions. Repositories do not commit. Domain objects do not commit. Network adapters do not commit.

```text
Entrypoint
    ↓
Application use case
    ↓
Unit of Work begins
    ↓
Read and lock required state
    ↓
Apply domain policy
    ↓
Persist state and durable effects
    ↓
Commit
    ↓
Return result DTO
```

### 7.2 Module-scoped Unit of Work

A normal use case that changes one module uses a module-scoped Unit of Work.

Example:

```python
class PromoUnitOfWork(Protocol):
    reservations: PromoReservationRepository

    async def __aenter__(self) -> "PromoUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
```

The Unit of Work exposes only repositories required by that module and that use-case family. It is not a global registry of all repositories.

### 7.3 Cross-module atomic workflow

Some operations legitimately require one PostgreSQL commit across multiple ownership boundaries. Examples may include:

- completing a tournament and granting an economy reward;
- refunding a purchase while changing entitlement and ledger state;
- recording a competition result together with a durable outgoing notification command.

Such an operation is implemented in `app/workflows/<workflow_name>/`.

A workflow:

- owns one transaction;
- defines narrow use-case-specific ports;
- may coordinate multiple module-owned adapters through one SQLAlchemy session;
- does not import module ORM models directly;
- does not expose a global cross-system UoW;
- is created only when atomicity is a verified business requirement.

Example contract:

```python
class CompleteTournamentTransaction(Protocol):
    competition: CompetitionCompletionPort
    rewards: RewardGrantPort
    outgoing_messages: OutgoingMessagePort

    async def __aenter__(self) -> "CompleteTournamentTransaction": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
```

The concrete SQLAlchemy adapter can use one session underneath all three ports. The application workflow sees only business-shaped operations.

### 7.4 Workflow governance and anti-god-module limits

`app/workflows/` is a controlled exception boundary, not the default home for orchestration.

Every workflow must document:

- the exact invariant that requires one commit;
- why eventual consistency is unacceptable;
- participating modules and module-owned ports;
- rows/locks acquired and expected transaction duration;
- idempotency strategy;
- why the behavior does not belong to one existing bounded module.

Hard constraints:

- a workflow may coordinate at most **three** business modules;
- a workflow must not import or call another workflow;
- a workflow must not contain Telegram, HTTP, Celery or Redis transport branching;
- a workflow must not expose repositories as a general service locator;
- each workflow has one command/use case and one explicit transaction contract;
- workflow-to-module edges are allowlisted in architecture contracts.

Review triggers:

- proposing a fourth participating module blocks implementation until the domain boundary is reconsidered;
- proposing the sixth active workflow package triggers a mandatory review of whether repeated workflows indicate a missing business module;
- a workflow that accumulates unrelated commands is split or reclassified before new behavior is added.

These limits are intentionally simple and enforceable. A deadline is not evidence that atomicity is required.

### 7.5 Decision rule: atomic workflow or integration event

Use one atomic workflow when **all** are true:

- the states are stored in the same PostgreSQL database;
- partial commit would violate a named business invariant;
- the operation is bounded and understandable as one transaction;
- no more than three business modules participate;
- locks and transaction duration remain acceptable;
- no external network call is required before commit.

Use a durable integration event when **any** are true:

- eventual consistency is acceptable;
- the receiving operation has an independent retry lifecycle;
- the work is expensive or external;
- the receiving module can process idempotently;
- keeping one transaction would create wide locks or coupling without protecting a real invariant;
- the operation would require more than three modules in one workflow.

This decision is recorded in the slice record and must not be chosen ad hoc inside implementation code.

### 7.6 Failed flush and conflict recovery

After SQLAlchemy raises `IntegrityError` during `flush`, the transaction is considered unusable unless a savepoint isolated the failure.

Allowed recovery patterns:

1. use `begin_nested()` and handle conflict within a savepoint;
2. exit and roll back the failed transaction, then retry in a new transaction;
3. use a PostgreSQL upsert or conflict-safe statement where semantics allow it.

Forbidden pattern:

```text
flush raises IntegrityError
→ catch exception
→ query using the same failed transaction
```

Real PostgreSQL integration tests are mandatory when the slice contains conflict recovery, uniqueness races or locking semantics. They are not required merely because a low-risk slice writes ordinary rows.

---

## 8. External I/O ordering

### 8.1 Hard rule

The following must never occur inside an open database transaction:

- Telegram send, edit or delete;
- HTTP calls;
- Celery enqueue;
- calls to Telegram Stars or another provider;
- ops alert HTTP delivery.

The transaction may only persist business state and a durable command/event describing work to perform after commit.

### 8.2 Why

Network I/O inside a transaction causes:

- long-held row or advisory locks;
- ambiguous send-success/commit-failure outcomes;
- duplicate or lost notifications;
- broker work starting before the source transaction commits;
- poor retry semantics;
- hidden coupling between business mutation and provider availability.

### 8.3 Allowed post-commit behavior

After commit, an entrypoint may directly perform an **ephemeral** effect that is safe to lose and does not consume a durable quota, reward, entitlement or notification marker.

Everything else must be represented durably before commit.

---

## 9. Events: exact meaning

### 9.1 Domain event

A domain event:

- belongs to one module;
- is created by domain logic;
- is handled synchronously inside the same application operation;
- shares the same transaction;
- is not published through Redis, Celery or an in-memory global bus;
- is not used to communicate between modules.

Its purpose is local decoupling and explicit domain behavior, not transport.

### 9.2 Integration event

An integration event:

- crosses a module boundary asynchronously;
- is persisted in PostgreSQL in the same transaction as the source business change;
- is consumed after commit by a dispatcher;
- has a stable event type and versioned payload;
- has an idempotency key;
- has retry, lease and failure visibility;
- is handled idempotently by the receiver.

No critical cross-module event may rely on in-memory pub/sub or “commit, then enqueue” without a durable record.

### 9.3 No generic event platform

The first implementation supports only the event types required by migrated slices. It consists of:

- one durable table or a deliberately reused and corrected table;
- one claim/retry protocol;
- explicit event handlers;
- no dynamic plugin discovery;
- no arbitrary event choreography language;
- no separate service.

---

## 10. Incoming Telegram processing protocol

The incoming update pipeline uses a durable processing lease rather than only an age-based status.

### 10.1 States

```text
RECEIVED
PROCESSING
PROCESSED
RETRY
FAILED
```

### 10.2 Required fields

At minimum:

```text
update_id
status
attempt_count
claim_token
claimed_at
lease_until
heartbeat_at
next_retry_at
processed_at
last_error_code
last_error_summary
created_at
updated_at
```

Raw secrets and sensitive headers are not stored.

### 10.3 Claim algorithm

1. Persist payment evidence and incoming update identity before broker enqueue, preserving the current strong durability property.
2. A worker claims an eligible row with a unique `claim_token`.
3. The claim sets `PROCESSING`, `claimed_at`, `lease_until` and increments `attempt_count`.
4. Long-running processing refreshes `heartbeat_at` and `lease_until` at a bounded interval.
5. A second worker may reclaim only after lease expiry.
6. Completion uses compare-and-set on the current `claim_token`.
7. Retryable failures set `RETRY` and `next_retry_at`.
8. Terminal failures set `FAILED` and become visible to operations.

### 10.4 Delivery trigger repair

Observability must not merely alert on stale incoming work. A scheduled repair task re-enqueues eligible `RECEIVED`, `RETRY` and expired `PROCESSING` rows.

The repair operation itself is idempotent. Multiple enqueues are acceptable because the claim protocol serializes processing.

---

## 11. Outgoing delivery protocol

### 11.1 Guarantee

Critical outgoing Telegram delivery provides:

```text
at-least-once processing with idempotent business state
```

Exactly-once Telegram message delivery is not claimed because Telegram `sendMessage` does not accept an application idempotency key. A process can crash after Telegram accepted a message but before PostgreSQL records `SENT`.

The design prevents duplicate rewards, debits, quota consumption and game-state transitions. It minimizes, observes and accepts the remaining possibility of a duplicate message in the provider acknowledgement crash window.

### 11.2 Effect classes

Every external effect is classified before implementation.

#### Critical

Examples:

- payment and refund confirmation;
- entitlement or reward result;
- final tournament result;
- message whose absence would hide a committed ticket, quota or purchase outcome.

Requirements:

- durable outgoing row in the source transaction;
- retry protocol;
- operator visibility;
- stable idempotency key;
- receiver-side or business-side idempotency.

#### Recoverable

Examples:

- Arena result display;
- friend challenge result;
- proof card;
- Daily Cup notification;
- referral reward notification.

Requirements:

- durable outgoing row;
- bounded retries;
- replay endpoint or repair task;
- failure visibility.

#### Ephemeral

Examples:

- typing indicator;
- temporary acknowledgement;
- nonessential menu refresh;
- low-value reminder with no consumed business resource.

Requirements:

- send only after commit;
- failure may be logged without durable retry;
- must not set “sent” or consume quota before actual send.

### 11.3 Outgoing row fields

At minimum:

```text
id
effect_type
aggregate_type
aggregate_id
recipient_key
payload_version
payload
idempotency_key
status
attempt_count
claim_token
claimed_at
lease_until
next_retry_at
provider_message_id
sent_at
last_error_code
last_error_summary
manual_replay_count
last_replayed_at
last_replayed_by
last_replay_reason
created_at
updated_at
```

A unique constraint protects `idempotency_key` within the chosen namespace.

### 11.4 States

```text
PENDING
CLAIMED
RETRY
SENT
FAILED
SKIPPED
```

`SKIPPED` is terminal only for an explicit business/provider reason, not as a generic exception sink.

### 11.5 Claim and send algorithm

1. The source application transaction inserts the outgoing row together with the business mutation.
2. Dispatcher selects eligible rows with `FOR UPDATE SKIP LOCKED`.
3. It writes a random `claim_token`, `claimed_at`, `lease_until`, sets `CLAIMED`, and commits the short claim transaction.
4. It performs Telegram I/O outside a database transaction.
5. On success, it records `provider_message_id`, `sent_at` and `SENT` using compare-and-set on `claim_token`.
6. On a retryable provider or network error, it records `RETRY`, increments attempts, calculates bounded backoff and clears the claim.
7. On a terminal provider error, it records `FAILED` or `SKIPPED` using a documented error classification.
8. On process death after claim, another dispatcher reclaims after `lease_until`.
9. On process death after provider success but before `SENT`, retry may produce a duplicate Telegram message. The row remains linked to one business effect and can never repeat the business mutation.

### 11.6 Dispatcher runtime topology

The initial production dispatcher uses the existing Celery deployment. It does **not** introduce a new permanent process.

Physical topology:

```text
source transaction commits outgoing row
        │
        ├─ best-effort post-commit enqueue: dispatch_outgoing_row(row_id)
        │                                  to q_delivery
        │
        └─ PostgreSQL remains source of truth

Celery Beat every 5 seconds
        ↓
scan_due_outgoing_delivery(batch_limit=50)
        ↓
q_delivery on existing Celery worker deployment
        ↓
claim / send / CAS completion
```

Operational rules:

- add a dedicated `q_delivery` queue;
- the existing worker deployment consumes `q_delivery,q_high,q_normal,q_low` with prefetch `1`;
- immediate post-commit enqueue is a latency optimization, not the durability mechanism;
- failure to enqueue after commit is logged but does not fail the committed business operation;
- the five-second scanner repairs missed enqueue and due retries;
- the scanner uses a supporting partial index and bounded batches;
- only one scan task performs the due-row selection at a time, using a short advisory lock or equivalent single-run guard;
- provider I/O never occurs in the beat task transaction.

Initial service targets:

- critical outgoing rows: p95 claim delay below 5 seconds;
- no due critical row older than 30 seconds without alerting;
- no sustained `q_delivery` backlog above 100 due rows for 5 minutes.

A separate dedicated delivery-worker process is introduced only if measured queue delay or backlog violates these targets after query/index and worker-routing tuning. This keeps the initial topology simple while preserving a clear scaling path.

### 11.7 Backoff and attempts

The exact numbers are configuration, but the policy must include:

- bounded exponential backoff with jitter;
- a maximum attempt count;
- a maximum retry age for time-sensitive messages;
- separate treatment for `RetryAfter`;
- no infinite `PENDING` state;
- a manual replay action for approved terminal failures.

### 11.8 Manual replay and idempotency

Manual replay operates on the **same outgoing row** and preserves the same `idempotency_key`.

Approved replay performs an audited compare-and-set transition:

```text
FAILED or SKIPPED
→ RETRY
```

It clears terminal error fields as appropriate, sets `next_retry_at`, increments `manual_replay_count`, and records operator, time and reason. It does not create a cloned row and does not repeat the source business mutation.

If the operator intentionally wants a new, separate message for the same aggregate, that is a new business effect with a new effect identity and idempotency key. It is not called replay and may reference the prior row through `supersedes_outgoing_id` or equivalent audit metadata.

### 11.9 Operator visibility ships with the dispatcher

The first production release of the dispatcher must include:

- counts by `PENDING`, `CLAIMED`, `RETRY`, `FAILED`;
- oldest row age;
- stale lease count;
- attempts distribution;
- recent error classes;
- an admin view or operational command to inspect failed rows;
- safe replay for one row or a bounded set;
- alerts for age and volume thresholds;
- audit history for replay, suppress and terminal classification.

A dispatcher without this visibility is incomplete.

---

## 12. Rendering and presentation

Application use cases do not return aiogram keyboards, Telegram messages or FastAPI responses. They return DTOs describing the business outcome.

Example:

```python
@dataclass(frozen=True)
class ArenaCompletionResult:
    duel_id: UUID
    winner_user_id: int
    challenger_score: int
    opponent_score: int
    reward_granted: int
    replay: bool
```

A Telegram presenter converts the DTO or a durable outgoing payload into:

- localized text;
- keyboard markup;
- message edit/send decision.

Workers must not import bot handlers, bot application construction or handler-owned keyboards. Shared Telegram presentation belongs to a Telegram adapter package, not to business modules or tasks.

---

## 13. Entrypoints and workers

### 13.1 FastAPI routes

A route may:

- validate transport input;
- authenticate and authorize;
- build a command/query;
- invoke one application use case;
- map result/error types to HTTP responses.

A route must not:

- import ORM models for writes;
- import repositories;
- open `SessionLocal.begin()`;
- send Telegram messages;
- enqueue Celery work before source commit;
- contain business saleability, reward or competition policy.

### 13.2 Telegram handlers

A handler may:

- parse update/callback data;
- invoke a use case;
- invoke an ephemeral presenter after commit;
- convert application errors to user-facing responses.

A handler must not:

- own transaction boundaries;
- query repositories directly;
- import worker tasks as business collaborators;
- mark a notification/quota as consumed before best-effort send;
- execute provider I/O while a transaction is open.

### 13.3 Celery tasks

A task is a transport adapter:

```python
@celery_app.task(name="promo.expire_reservations")
def expire_promo_reservations() -> None:
    container.expire_promo_reservations.execute()
```

A task must not:

- import ORM models or repositories;
- construct Telegram business messages itself;
- own policy decisions;
- keep an open transaction during provider I/O;
- duplicate a use case already exposed elsewhere.

Task-level retry is used only for failures appropriate to the task transport. Durable business retry remains in PostgreSQL state.

---

## 14. Read-only query policy

A controlled CQRS-lite path is allowed:

```text
HTTP route → query service → SQL read model → immutable DTO
```

This exception is limited by the following rules:

1. Query services live in an explicit `queries` package.
2. They never mutate state.
3. They never return ORM entities outside the adapter/query boundary.
4. They do not share a session with a write use case.
5. They do not call write repositories.
6. They may use optimized SQL projections and joins.
7. Each query family is listed in the architecture allowlist.
8. Bot handlers and Celery mutation flows cannot use the exception to bypass application use cases.
9. A query that decides eligibility, saleability, reward, authorization or a state transition is not “read-only reporting”; that policy belongs in application/domain code.

The purpose is efficient admin and analytics reads, not a general escape hatch for direct ORM access.

---

## 15. Composition roots and process state

### 15.1 Explicit runtime construction

There are separate composition roots for:

- API process;
- Telegram update worker;
- Celery worker/beat;
- CLI and maintenance scripts.

Example shape:

```text
bootstrap/api.py
bootstrap/telegram_worker.py
bootstrap/celery_worker.py
```

They create and wire:

- settings;
- SQLAlchemy engine/session factory;
- Redis clients;
- Telegram clients;
- Unit of Work factories;
- use cases;
- dispatchers;
- observability adapters.

### 15.2 Lifecycle

FastAPI lifespan and worker lifecycle hooks explicitly:

- initialize resources;
- validate required dependencies;
- close Redis clients;
- close Telegram HTTP sessions;
- dispose the SQLAlchemy engine;
- stop background dispatch loops cleanly where applicable.

Importing a module must not create the production engine, app-wide clients or a hidden dispatcher as an unavoidable side effect.

### 15.3 Process-local state policy

State that must be consistent across API workers or Celery processes cannot live in a process-local dict.

The following known cases are migrated to Redis or PostgreSQL before being considered resolved:

- ops throttle currently split across four API workers;
- Daily Cup cooldown map that is unbounded and not shared across Celery child processes.

A composition root is not a wrapper around incorrect process-local state. The storage semantics must match the runtime topology.

---

## 16. Security release blocker

The following findings are not architecture backlog. They are a separate immediate security release and block architecture migration work:

1. Existing TOTP secret must not be returned to a password-only pending principal.
2. Refresh tokens require rotation, unique session/token identity and replay detection.
3. Logout must attempt revocation of access and refresh independently and report/handle partial failure correctly.
4. Refresh must revalidate current admin identity, role and enabled state rather than treating stale claims as authoritative.

Required tests include:

- pending principal cannot read an enrolled TOTP secret;
- predecessor refresh cannot be replayed after rotation;
- concurrent refresh behavior is deterministic;
- logout revokes both token identities even if one revocation operation fails;
- role/email/disabled-state changes invalidate or update refresh behavior.

This work is shipped and verified independently before the first architecture pilot.

---

## 17. Analytics source of truth

The three divergent metrics paths must not remain authoritative in parallel.

Before broad module migration:

1. Define one canonical meaning for active user, DAU, WAU and MAU.
2. Select one authoritative persistence pipeline or live-query contract.
3. Mark other tables/pipelines as deprecated or non-authoritative.
4. Update admin readers to the canonical source.
5. Add reconciliation checks during transition.
6. Remove unused writers/readers after a measured compatibility period.

A metric shown to an operator must include:

- definition;
- data source;
- aggregation timezone;
- freshness timestamp.

The `celery` Redis list is not to be presented as a failed queue unless a real DLQ is configured. Webhook health is not inferred solely from recent traffic.

---

## 18. Architecture and migration enforcement

### 18.1 Dependency tooling decision

Dependency rules are enforced by a mature Python architecture-testing tool integrated into pytest or CI. Existing shell/regex/partial-AST scripts may remain as secondary diagnostics but are not the source of truth.

The chosen tool must correctly handle:

- relative imports;
- local imports inside functions;
- `__init__.py` re-exports;
- package contracts;
- Windows and Linux path semantics;
- forbidden third-party dependencies by layer.

### 18.2 Initial dependency contracts

The first enforced contracts are:

```text
domain must not import sqlalchemy, aiogram, fastapi, celery or redis
application must not import aiogram, fastapi or celery
entrypoints must not import SessionLocal or ORM write models
workers must not import bot handlers or handler keyboards
module A must not import module B adapters or persistence
legacy packages must not import newly migrated private adapters
workflows must not import other workflows
workflow module-contract edges must be explicitly allowlisted
```

### 18.3 Ratchet strategy

Rules apply immediately to newly migrated packages. Legacy violations are recorded in a baseline and may not grow.

A slice is not complete until:

- its new package passes strict contracts;
- no new legacy dependency violation is introduced;
- any temporary bridge is registered with owner, review date and removal condition.

### 18.4 Migration flag registry

Every legacy/new routing flag is registered in one machine-readable file, for example:

```text
docs/architecture/migration_registry.yaml
```

Each entry contains:

```text
flag
slice
risk_tier
legacy_entrypoint
new_entrypoint
created_at
full_cutover_at
review_by
removal_condition
rollback_command_or_setting
legacy_usage_metric
owner
```

Enforcement rules:

- code may not introduce a migration flag without a registry entry;
- `review_by` must be set and may not be silently extended without a recorded reason;
- CI fails when a registry deadline is expired;
- CI fails when a registered flag no longer exists in code or a code flag has no registry entry;
- at most **two** active dual-path write migrations are allowed at once;
- a third dual path requires closing one existing migration or adding an explicit decision amendment;
- after full cutover, legacy usage is measured until the risk-tier observation period is complete, then legacy removal is mandatory.

A small deterministic registry validator is acceptable here because it validates explicit data and dates, not Python import semantics.

---

## 19. Risk-scaled test strategy

### 19.1 Slice risk tiers

Every slice is classified before implementation.

| Tier | Description | Typical examples |
|---|---|---|
| `R1 — Low` | one module, no money/reward/quota, no durable provider effect, no concurrency invariant change | promo reservation expiry, simple cleanup or query migration |
| `R2 — Stateful` | user-visible mutation, locking/idempotency/concurrency semantics, or recoverable delivery, but no monetary entitlement | referral qualification, friend caps, noncritical notification |
| `R3 — Critical` | money, entitlement, reward, quota/ticket consumption, final competition state, payment/refund, or critical durable delivery | Arena completion with reward, Daily Cup result, payments reliability |

Risk is determined by business consequence, not by file size.

### 19.2 Characterization first

Before moving a use case, create characterization coverage for current externally visible behavior and important database outcomes.

A migration must distinguish:

- preserved behavior;
- intentional bug fix;
- intentional product-policy change.

They cannot be mixed silently.

### 19.3 Test layers

#### Domain/application unit tests

Required for all tiers when business branching or policy is moved.

- framework-free;
- use fake clocks and deterministic IDs where useful;
- may use an in-memory fake UoW for business branching;
- assert commands, outcomes and idempotency behavior.

#### Port contract tests

Required when a new reusable port has nontrivial behavioral semantics. A trivial one-method adapter may be covered by one real-adapter integration test instead of a duplicated fake/real contract suite.

#### PostgreSQL integration tests

Required only for database semantics the slice actually depends on:

- row/advisory locking;
- uniqueness and partial indexes;
- savepoint/conflict recovery;
- concurrent creates;
- idempotency races;
- outbox claim with `SKIP LOCKED`;
- stale lease reclaim.

For `R1`, one real PostgreSQL happy-path integration test is sufficient unless the slice changes one of those semantics. SQLite or mocks are never substitutes when PostgreSQL-specific behavior is under test.

#### Failure-window tests

Test only applicable crash points.

Possible points include:

```text
before business commit
after business commit before dispatcher sees work
after claim before send
after Telegram success before SENT update
after retry state write
on stale lease reclaim
after IntegrityError flush
```

`R1` slices without external effects do not implement artificial Telegram or outbox failure tests. `R2` covers relevant commit/concurrency/provider boundaries. `R3` covers every material crash point and proves that business state is neither duplicated nor lost.

#### Entrypoint integration test

At least one real FastAPI, aiogram or Celery adapter-path test is required for `R2` and `R3`. For `R1`, a direct Celery-task wiring test or equivalent focused entrypoint test is sufficient.

### 19.4 Existing tests

Existing large monkeypatch-heavy tests are not rewritten wholesale. For a migrated slice:

1. retain useful characterization coverage;
2. move policy assertions to application tests;
3. move persistence semantics to PostgreSQL contract/integration tests;
4. reduce transport tests to mapping and wiring;
5. delete obsolete monkeypatch scaffolding only after equivalent coverage exists.

The test migration follows production slices and does not become a separate repository-wide rewrite.

### 19.5 Default rigor matrix

| Requirement | R1 Low | R2 Stateful | R3 Critical |
|---|---:|---:|---:|
| Characterization | focused | required | required and explicit bug/policy split |
| Framework-free application tests | when policy exists | required | required |
| Real PostgreSQL | one happy path; more only if semantics require | relevant locks/conflicts | full relevant locking, race and recovery set |
| Failure-window tests | only actual local commit boundary | relevant boundaries | all material crash points |
| Feature flag | optional; git/task-route revert may suffice | normally required | required |
| Shadow comparison | not required | when cheap and pure | required when a pure comparison is possible |
| Observability | structured result/counter | state/error metrics | full operational contract and alerts |
| Legacy observation | direct cleanup or short observation | minimum 7 days at full cutover | minimum 14 days and one full relevant business cycle |

The matrix is a default. A slice may be promoted to a higher tier, but reducing rigor requires an explicit reason in its slice record.

---

## 20. Safe cutover, shadow evidence and rollback

### 20.1 Feature flags

Every `R2` or `R3` behavior-changing migrated write path is protected by a server-side feature flag at the use-case routing boundary.

For `R1`, a flag is optional when all are true:

- schema is additive;
- the old implementation can be restored by one task-route/config change or clean git revert;
- no user-visible or monetary ambiguity exists;
- no dual-write is required.

A flag selects either the legacy or new implementation. The two write paths are never executed simultaneously for the same request.

### 20.2 Shadow mode

Shadow execution is permitted only for pure or read-only calculations:

- eligibility decisions;
- selected question IDs from a fixed snapshot;
- computed reward plan before applying it;
- rendered DTO comparison;
- analytics query comparison.

Shadow mode must not:

- commit mutations;
- send Telegram messages;
- consume quotas;
- enqueue work;
- acquire conflicting long-lived locks.

### 20.3 Shadow comparison storage

For `R2` flows, low-volume structured logs and aggregate counters are sufficient unless the slice record requires row-level investigation.

For `R3` flows, comparisons are stored in one bounded PostgreSQL table, for example `architecture_shadow_comparisons`, with:

```text
id
slice_key
comparison_type
correlation_key_hash
cohort
legacy_digest
new_digest
difference_code
bounded_context
created_at
resolved_at
resolution
```

Rules:

- raw Telegram payloads, payment tokens, TOTP data and unnecessary personal content are never stored;
- comparable results are canonicalized before hashing;
- `difference_code` uses a bounded enum, not arbitrary exception text;
- detailed rows are retained for 30 days, then deleted or aggregated;
- dashboards expose comparison count, mismatch rate and unresolved mismatch classes;
- the slice record defines the acceptable mismatch threshold;
- default threshold is zero for money, entitlement, reward and invariant decisions, except for explicitly approved intentional behavior changes.

This table is evidence for cutover, not a second analytics platform.

### 20.4 Rollout sequence

For a nontrivial live flow:

1. characterization tests;
2. new implementation disabled in production;
3. pure shadow comparison where possible;
4. internal/admin users;
5. small percentage or deterministic user cohort;
6. expanded cohort;
7. full cutover;
8. risk-tier observation period;
9. legacy removal and flag deletion.

### 20.5 Rollback

Rollback means changing the routing flag back to the legacy implementation. It must not require a database downgrade.

Database migrations for a slice are therefore additive until the legacy path is removed:

- add new columns/tables/indexes;
- dual-read only when explicitly designed;
- avoid destructive renames/removals during rollout;
- remove obsolete schema in a later cleanup release.

### 20.6 Legacy cleanup enforcement

Temporary duplication is controlled, not merely documented.

- every dual path is in the migration registry from section 18.4;
- only two dual-path write migrations may coexist;
- after full cutover, the legacy path emits a usage counter;
- `R2` legacy code is removed after at least 7 stable days with no unexpected fallback;
- `R3` legacy code is removed after at least 14 stable days and one complete relevant business cycle;
- an expired `review_by` date fails CI;
- cleanup includes deleting the flag, legacy router branch, dead tests, obsolete registry entry and later-unused schema;
- a deliberate extension requires a short amendment containing reason, new date and risk.

`R1` should normally avoid dual implementations entirely and use a small reversible cutover.

---

## 21. Migration plan and stop gates

### 21.1 Execution model for a solo-maintained product

This roadmap is a sequence of independent value units, not a commitment to complete every slice continuously.

Rules:

- only one architecture migration slice is active at a time;
- product growth, deployment blockers and incidents may pause the roadmap after any completed slice;
- pausing after Release 1, Slice 1 or Slice 3 is a valid success state;
- the next slice starts only when it closes a current risk or directly enables planned product work;
- no long-lived migration branch is used; each slice must produce a deployable or cleanly discardable increment.

Default reassessment timeboxes:

- `R1`: reassess after 2 focused developer days without a deployable increment;
- `R2`: reassess after 5 focused developer days;
- `R3`: decompose into deployable sub-slices; no sub-slice may run longer than 5 focused developer days without a checkpoint.

When a timebox is exceeded, implementation stops before expanding scope. The decision is one of:

1. simplify the slice;
2. split it;
3. retain the proven partial infrastructure and defer the behavior migration;
4. abandon the slice and keep the legacy path.

Partial execution is not failure. The architecture remains useful after every completed release or slice.

### Release 0 — security remediation

**Goal:** close AR-001 through AR-004 before architecture work.

Deliverables:

- safe TOTP enrollment/recovery semantics;
- rotating refresh sessions with replay protection;
- complete logout revocation behavior;
- current identity/role validation;
- security regression tests;
- production release and verification.

Exit criterion: all four findings are closed and independently deployed.

### Release 1 — cheap correctness and operational truth

**Goal:** remove known correctness issues that should not wait for module migration.

Deliverables:

- canonical analytics definitions and source;
- correction of queue and webhook health semantics;
- Redis-backed ops throttle;
- Redis- or DB-backed bounded Daily Cup cooldown;
- fix failed-flush recovery paths;
- real PostgreSQL tests for those paths;
- install mature architecture-contract tooling for the pilot.

Exit criterion: admin numbers have one documented source of truth; known process-local state defects and aborted-transaction queries are closed.

**Pause gate:** after Release 1, reassess product priorities. Continuing the architecture roadmap is optional.

### Slice 1 — promo reservation expiry pilot (`R1`)

**Why first:** low state complexity, no Telegram delivery, one module, scheduled entrypoint, easy equivalence testing.

Target flow:

```text
Celery task
    ↓
ExpirePromoReservations use case
    ↓
PromoUnitOfWork
    ↓
PromoReservationRepository port
    ↓
SQLAlchemy adapter
```

Deliverables:

- first real module-scoped application use case;
- explicit transaction ownership;
- SQLAlchemy adapter;
- thin Celery entrypoint;
- architecture contract for the new package;
- focused characterization and framework-free application tests;
- one real PostgreSQL integration test for the actual expiry update;
- direct reversible task routing or a flag only if needed;
- immediate legacy removal after equivalence is proven, unless production rollback genuinely requires a short dual path.

Not required for this pilot:

- Telegram/outbox crash-window tests;
- a generic fake/real contract suite for a trivial adapter;
- shadow comparison infrastructure;
- payment-grade operational dashboards.

Exit criterion: no `SessionLocal`, ORM model or policy logic in the Celery task; behavior and expired-row counts match the legacy path.

**Pause gate:** if the pilot does not reduce implementation/test complexity, stop and revise the architecture before migrating another behavior.

### Slice 2 — referral qualification (`R2`)

**Goal:** prove a richer single-module use case with locking/idempotency but without introducing the full Telegram dispatcher.

The business qualification and reward state transition are separated from notification. Notification may initially remain on the legacy path if it cannot yet meet durable delivery requirements.

Exit criterion: business mutation is application-owned and idempotent; failed notification cannot change reward correctness.

### Slice 3 — durable outgoing delivery foundation (`R3` infrastructure)

**Goal:** implement the exact protocol and runtime topology in section 11.

Deliverables:

- schema and migration;
- `q_delivery` routing in the existing Celery deployment;
- best-effort immediate dispatch plus five-second repair scanner;
- claim/lease/retry state machine;
- Telegram adapter;
- scheduled repair/reclaim;
- admin/ops visibility and alerts;
- same-row manual replay with audit;
- provider crash-window tests;
- one low-risk recoverable message migrated end to end.

Exit criterion: there is a real production consumer, stale recovery and operator visibility. No orphan repository primitives remain without a caller.

**Major pause gate:** after Slice 3, reassess whether current product usage and incident history justify continuing into Arena, friend challenges and tournaments. The system may remain at this state indefinitely.

### Slice 4 — referral reward notification (`R2`)

**Goal:** close the current “notified before delivery” failure mode.

Deliverables:

- reward state and outgoing notification recorded atomically where required;
- delivery after commit;
- retry and same-row manual replay;
- no `notified_at` terminal marker before successful or explicitly terminal delivery state.

Exit criterion: a provider failure does not permanently hide a granted reward notification.

### Slice 5 — Arena completion (`R3`)

Arena is migrated only after slices 1–4 prove the patterns.

Before migration, separately characterize and fix/specify:

- replay result semantics;
- terminal result rendering;
- notification failure behavior;
- reward atomicity;
- exact business policy for duplicate message tolerance.

Target design:

- an explicit cross-module atomic workflow only if competition completion, reward and outgoing effect must share one PostgreSQL commit;
- workflow governance limits from section 7.4 apply;
- Telegram delivery through the durable outgoing protocol;
- no send inside advisory-lock transaction;
- replay returns a complete terminal result DTO;
- feature-flag cutover with PostgreSQL shadow comparison for computed result/reward.

Exit criterion: AR-011, AR-012 and relevant delivery gaps are closed with PostgreSQL and failure-window tests.

### Slice 6 — friend challenges (`R3` where quota/reward is involved)

Focus:

- quota timing;
- deadline notification markers;
- proof-card enqueue gaps;
- serialization of cap checks;
- durable delivery and replay.

Exit criterion: quotas are not permanently consumed by failed best-effort sends; concurrent cap tests pass.

### Slice 7 — Daily Cup and private tournaments (`R3`)

Focus:

- pre-commit enqueue removal;
- no Telegram I/O inside lifecycle transactions;
- batch delivery persistence per item rather than only after whole-batch success;
- durable round/result/proof delivery;
- clear cross-module reward workflow.

Exit criterion: a mid-batch crash leaves individually recoverable delivery state.

### Slice 8 — payments reliability decomposition (`R3`)

Preserve the existing `PAID_UNCREDITED` checkpoint and database invariants while separating:

- provider fetch;
- reconciliation policy;
- purchase recovery;
- entitlement credit;
- refund policy;
- manual review;
- audit events;
- alerting.

Critical payment behavior remains protected by additive migration, idempotency keys and real database integration tests.

Exit criterion: the 792-line responsibility hotspot is decomposed by behavior, not merely split by file size, and all payment recovery invariants remain covered.

### Later optional slices

- remaining gameplay sessions and Daily flows;
- incoming Telegram lease/heartbeat rollout to all updates;
- admin query separation;
- cleanup of old packages and architecture baselines;
- final removal of obsolete metrics and delivery tables only after migration.

None of these is automatically authorized by completion of the previous slice. Each requires a fresh value/risk decision.

---

## 22. Slice decision template

Every architecture slice contains one small record with these fields:

```text
Business behavior
Risk tier: R1 / R2 / R3
Current entrypoint
Owning module
Expected independent value
Default timebox and reassessment point
Transaction owner
Locked rows/invariants
Cross-module decision: local use case / atomic workflow / integration event
If workflow: exact invariant, participating modules, why eventual consistency is invalid
External effects and their class
Dispatcher/queue path when applicable
Idempotency key
Manual replay semantics
Crash points and expected recovery
Feature flag or simpler rollback path
Shadow comparison storage and cutover threshold when applicable
Characterization tests
Required PostgreSQL/concurrency tests
Observability level
Migration registry entry when dual path exists
Legacy observation period and removal condition
Stop/defer condition
```

The record should remain short. Its purpose is to force the few irreversible protocol decisions into writing, not to create a second specification document.

---

## 23. Risk-scaled Definition of Done

### 23.1 Mandatory for every migrated slice

A slice is done only when all applicable common statements are true:

- one application use case owns the transaction;
- entrypoints contain transport mapping only;
- repositories do not commit;
- no provider or broker I/O occurs inside the transaction;
- cross-module coordination follows the recorded local/workflow/event decision;
- business operations are idempotent where duplicate execution is possible;
- architecture contracts pass on Windows and CI/Linux;
- documentation reflects actual runtime ordering;
- the slice record states its risk tier, rollback path and stop condition;
- any temporary bridge or flag is present in the migration registry.

### 23.2 R1 — Low

Required:

- focused characterization of current behavior;
- framework-free application test when policy is moved;
- one real adapter/entrypoint integration test;
- one PostgreSQL happy-path test for a database mutation;
- direct rollback by route/config or clean git revert;
- no unnecessary dual implementation;
- focused structured logging or result counter.

Not automatically required:

- full feature-flag cohort rollout;
- generic port contract suite;
- Telegram/provider failure matrix;
- shadow-diff table;
- payment-grade dashboards.

### 23.3 R2 — Stateful

Required in addition to common criteria:

- tests for every relevant lock, uniqueness, conflict or idempotency semantic;
- relevant commit/provider failure-window tests;
- server-side feature flag unless a simpler rollback is demonstrably safe;
- state/error metrics;
- at least 7 stable days at full cutover before legacy removal;
- one real entrypoint integration test.

### 23.4 R3 — Critical

Required in addition to common criteria:

- real PostgreSQL concurrency and recovery coverage for every material invariant;
- every material crash point tested;
- durable effect protocol and operator visibility when external delivery exists;
- feature flag and additive-schema rollback;
- shadow comparison for pure decisions when technically possible;
- mismatch threshold and cutover evidence;
- at least 14 stable days plus one complete relevant business cycle before legacy removal;
- alerting for stuck, failed or ambiguous state;
- auditable replay/suppress actions.

A slice is promoted to `R3` whenever it changes money, entitlement, reward, quota/ticket consumption, final competition state or critical user notification semantics.

### 23.5 Completion is value-based

A file move, package skeleton or interface-only refactor is not a completed slice. A slice is complete only when it independently reduces a documented risk, removes a concrete coupling, or enables a product behavior while preserving rollback.

---

## 24. Observability requirements

### 24.1 Asynchronous state machines

Every durable asynchronous state machine exposes:

- current counts per state;
- oldest age per nonterminal state;
- attempt count distribution;
- stale lease count;
- throughput and failure rate;
- top bounded error categories;
- last successful processing time;
- replay actions and their audit trail.

Every migrated durable use case records enough structured context to answer:

```text
Was the business mutation committed?
Was a durable effect created?
Was it claimed?
Was provider delivery attempted?
Was it acknowledged?
Is retry scheduled?
Did an operator replay or suppress it?
```

### 24.2 Shadow comparisons

For critical shadowed decisions, operations can answer:

```text
How many comparisons ran?
What percentage matched?
Which bounded mismatch classes remain?
Which cohort and code version produced them?
Were mismatches approved behavior changes or unresolved defects?
```

The authoritative row-level mechanism is the bounded `architecture_shadow_comparisons` table defined in section 20.3. Aggregate metrics may remain after detailed rows expire.

### 24.3 Migration state

The migration registry exposes:

- active flags;
- current rollout percentage/cohort;
- full-cutover date;
- legacy fallback usage;
- review deadline;
- removal status.

This makes temporary duplication visible instead of relying on memory.

Sensitive tokens, raw secrets and unnecessary payload contents are not logged or stored.

---

## 25. Trade-offs accepted

### 25.1 Modular monolith over microservices

Accepted because:

- core state shares one PostgreSQL database;
- strong cross-feature transactions already exist;
- operational complexity must remain manageable;
- the current problem is dependency and transaction ownership, not service deployment.

### 25.2 Explicit workflows over absolute module isolation

Some business invariants require one commit across ownership areas. Hiding this behind global repositories or pretending it is asynchronous would be less honest. Explicit workflow packages make the exception visible, while the three-module cap and workflow-count review prevent the exception from becoming a new god module.

### 25.3 At-least-once Telegram delivery

A duplicate Telegram message is possible in one unavoidable crash window. The alternative claim of exactly-once would be false. The design instead guarantees that business state is idempotent and that ambiguous deliveries are observable.

### 25.4 PostgreSQL outbox over direct broker enqueue

This adds a table and dispatcher but removes the commit-to-broker loss window and gives repair visibility. It is used only for effects that justify durability.

### 25.5 Existing Celery deployment before a new dispatcher process

The initial dispatcher uses `q_delivery`, immediate best-effort wake-up and a five-second PostgreSQL repair scan inside the existing Celery topology. This accepts a small polling cost to avoid a fifth production process. A separate process is introduced only from measured latency/backlog evidence.

### 25.6 Incremental duplication during migration

For a limited period, legacy and new implementations may coexist behind a routing flag. This temporary duplication is accepted to provide rollback, but it is enforced through the registry, a two-active-flag cap, CI review deadlines, usage metrics and mandatory risk-tier cleanup periods.

### 25.7 Risk-scaled rigor

Low-risk slices deliberately use a lighter completion bar than payments or competition results. This accepts that not every migration proves every infrastructure failure mode, while preserving full rigor wherever business consequence justifies it.

### 25.8 Pausable roadmap

The roadmap may stop after any completed unit. This accepts an incomplete repository-wide migration in exchange for protecting product development time and ensuring that every completed slice delivers standalone value.

---

## 26. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Architecture folders grow without behavior improvement | vertical slices only; value-based Definition of Done forbids file-move-only work |
| Low-risk pilot is buried under critical-flow ceremony | R1/R2/R3 rigor matrix and explicit Slice 1 exclusions |
| Global UoW becomes a service locator | module-scoped UoW; use-case-specific workflow transaction ports |
| `app/workflows/` becomes a new god module | maximum three modules per workflow, no workflow chaining, sixth-workflow review trigger, allowlisted edges |
| Outbox repeats existing orphan infrastructure | dispatcher, stale recovery and admin visibility ship in the same slice |
| Dispatcher creates unnecessary operational process | existing Celery topology first; dedicated process only from measured SLO breach |
| Poll scanner adds database pressure | partial index, five-second cadence, bounded batch, single-run guard and measured escalation |
| Duplicate Telegram message after provider success | acknowledge impossibility of exactly-once; idempotent business mutation; provider message ID; observability/manual resolution |
| Manual replay duplicates the business effect | same-row replay with same idempotency key; cloned row explicitly forbidden |
| Cross-module event loss | PostgreSQL-persisted integration event in source transaction |
| In-memory events become hidden coupling | domain events remain local and synchronous only |
| Read-only query exception spreads into writes | explicit queries package, immutable DTOs, allowlist and no shared write session |
| Shadow evidence is too vague for cutover | bounded PostgreSQL comparison table for R3, canonical digests, mismatch thresholds and retention |
| Legacy flags accumulate indefinitely | machine-readable registry, two-active cap, CI expiry checks, usage metrics and mandatory cleanup windows |
| New architecture breaks live gameplay | low-risk pilot first; feature flags; pure shadow only; additive schema; rollback path |
| Mocks hide PostgreSQL semantics | real PostgreSQL tests whenever locks/conflicts/provider state require them |
| Guards return false PASS | mature architecture-testing tool; cross-platform CI; legacy ratchet |
| Composition root preserves broken local state | migrate topology-dependent throttle/cooldown to Redis/PostgreSQL |
| Security debt waits behind refactor | separate blocking security release |
| Roadmap consumes product-development capacity indefinitely | one active slice, explicit timeboxes, pause gates and independent value per slice |

---

## 27. Explicit rejected alternatives

### 27.1 Arena as the first slice

Rejected because it combines architectural migration with known replay, transaction/delivery and crash-window defects. It is migrated only after the pattern is proven.

### 27.2 One global Unit of Work containing all repositories

Rejected because it erases module boundaries and becomes a service locator.

### 27.3 One Unit of Work per module for a required atomic operation

Rejected when it would allow partial commits that violate a real invariant. Use an explicit cross-module workflow transaction instead.

### 27.4 Unbounded `app/workflows/` escape hatch

Rejected because it would legalize a new orchestration god module. Workflows are capped, non-composable and review-triggered.

### 27.5 In-memory asynchronous event bus for critical work

Rejected because process failure between commit and publish loses the event.

### 27.6 Direct `commit → Celery enqueue`

Rejected for critical/recoverable effects because broker failure after commit loses work. Immediate enqueue remains only a best-effort latency optimization over a durable PostgreSQL row.

### 27.7 Telegram send inside a database transaction

Rejected because it holds locks and creates ambiguous provider/commit outcomes.

### 27.8 Exactly-once Telegram claim

Rejected as technically dishonest without provider-side idempotency support.

### 27.9 Manual replay by cloning an outgoing row

Rejected because it creates a second idempotency identity for one business effect and can bypass receiver-side deduplication.

### 27.10 A new permanent dispatcher process from the first release

Rejected because the current scale does not justify a fifth long-running component. Existing Celery topology is used until measured SLO evidence requires separation.

### 27.11 One maximum Definition of Done for every slice

Rejected because it makes the low-risk pilot as expensive as payments and encourages the migration to stall before reaching valuable flows.

### 27.12 Unlimited temporary feature flags

Rejected because unbounded legacy/new pairs become permanent ambiguity. Two active dual-path write migrations is the default hard cap.

### 27.13 New custom regex/partial-AST guards as primary enforcement

Rejected because existing scripts already miss real cycles and have platform-specific false passes.

### 27.14 Repository-wide folder migration before vertical slices

Rejected because it creates churn without proving transaction, retry or testing behavior.

### 27.15 All-or-nothing completion of the roadmap

Rejected because Quiz Arena is one of several actively maintained products. Every completed slice must stand on its own and the roadmap may pause indefinitely.

---

## 28. Mapping to major research findings

| Research area | Design response |
|---|---|
| AR-001–AR-004 admin security | blocking Release 0 |
| AR-005 process-local throttle | Redis-backed shared state in Release 1 |
| AR-006 `bot ↔ workers` cycle | thin entrypoints; workers cannot import handlers/keyboards; presentation adapter boundary |
| AR-007 transaction ownership | application-owned UoW/workflow; entrypoints cannot open transactions |
| AR-008 failed flush recovery | savepoint/new transaction/upsert rule plus PostgreSQL tests |
| AR-009/AR-010 concurrency gaps | module migration requires invariant and concurrent PostgreSQL tests |
| AR-011/AR-012 Arena replay/send ordering | delayed Arena slice with explicit terminal DTO and durable delivery |
| AR-013–AR-017 committed markers/enqueue gaps | durable effect in source transaction; send/enqueue after commit through dispatcher |
| AR-018 orphan repair primitives | dispatcher, repair and admin visibility delivered together |
| AR-019 send/mark crash window | explicit at-least-once guarantee and idempotent business state |
| AR-020/AR-023 sent/notified before delivery | delivery state owns success; no terminal business marker before actual outcome |
| AR-021 batch persistence gap | item-level recoverable delivery state |
| AR-022 incoming lease gap | claim token, heartbeat, lease expiry and scheduled repair |
| AR-024 evidence lifecycle drift | incoming state machine becomes authoritative and observable |
| AR-025 saleability in UI | domain/application policy, not handler |
| AR-028 misleading outbox | either correct and reuse with full protocol or introduce clearly named durable tables |
| AR-029 worker limits/health | runtime configuration and observability follow after ownership is clear; no silent infinite work |
| AR-030 divergent analytics | canonical source in Release 1 |
| AR-031 incorrect queue/health semantics | explicit operational definitions and real DLQ only if configured |
| AR-032/AR-033 global lifecycle/cooldown | explicit composition roots and shared bounded state |
| AR-034/AR-035 responsibility/test coupling | vertical decomposition and layered tests, not file-size-only splitting |
| AR-036 guard blind spots | mature cross-platform architecture contracts |
| AR-037 documentation drift | runtime docs updated as part of slice done criteria |
| AR-038 duplicate orchestration | one use case per behavior; legacy removed after cutover |
| Execution-risk critique: uniform ceremony | R1/R2/R3 Definition of Done and explicit pilot exclusions |
| Execution-risk critique: workflow growth | three-module cap, no chaining and sixth-workflow review trigger |
| Execution-risk critique: dispatcher topology | existing Celery `q_delivery`, immediate wake-up and five-second repair scanner |
| Execution-risk critique: replay identity | same-row replay with the same idempotency key |
| Execution-risk critique: legacy accumulation | migration registry, two-active cap, CI expiry and mandatory cleanup windows |
| Execution-risk critique: shadow evidence | bounded PostgreSQL comparison table and mismatch thresholds |
| Execution-risk critique: endless roadmap | timeboxes, pause gates and independent value per slice |

---

## 29. Final target

The desired runtime form for a migrated mutation is:

```text
Telegram / HTTP / Scheduler
            │
            ▼
      Thin entrypoint adapter
            │
            ▼
      Application use case
            │
       ┌────┴────┐
       ▼         ▼
 Domain policy   Ports
       │         │
       └────┬────┘
            ▼
  Module UoW or explicit workflow
            │
            ▼
 PostgreSQL state + durable effect
            │
          COMMIT
            │
            ▼
 Dispatcher / presenter / provider adapter
```

The target is achieved not when every file has been moved, but when the important flows have:

- clear business ownership;
- one transaction owner;
- no external I/O inside transactions;
- durable and observable critical effects;
- explicit cross-module semantics;
- safe rollout and rollback;
- tests that exercise real PostgreSQL and failure windows.

The execution is equally important: rigor scales with risk, workflow exceptions remain bounded, temporary dual paths expire automatically, dispatcher topology begins simple and scales from evidence, and the roadmap can pause after any independently valuable slice.

That is the practical meaning of modular Clean Architecture for Quiz Arena without unnecessary bureaucracy.
