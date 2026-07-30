# Quiz Arena — Modular Clean Architecture Implementation Plan

**Статус:** канонічний implementation backlog  
**Дата базової перевірки:** 2026-07-30  
**Режим виконання:** поступова міграція modular monolith; один невеликий PR за milestone  
**Джерела рішень:** фінальний ADR, повний architecture audit `AR-001`–`AR-040`, актуальний код репозиторію

Цей документ є планом, а не дозволом на весь roadmap одразу. Кожний milestone
потребує окремого завдання, перевірки актуального HEAD і виконання чинних
repository rules. За замовчуванням один розробник веде одну активну
behavioral migration; незавершений roadmap є допустимим станом.

Незмінні правила для всіх milestone:

- `Domain → Application → Adapters / Infrastructure`; vertical slice, а не
  repository-wide переміщення файлів.
- Application use case або explicit bounded cross-module workflow є єдиним
  transaction owner. Entrypoint, repository, presenter і transport не
  commit-ять.
- Telegram, HTTP, Redis, Celery enqueue й ops alert не виконуються всередині
  SQL-транзакції.
- Немає global Unit of Work, universal event framework, interface для кожної
  функції чи наперед створених порожніх layers.
- Зміни схеми під час rollout additive. Rollback перемикає routing, а не
  downgrade-ить БД.
- Routing flag обирає рівно один mutation/send path. Shadow ніколи не виконує
  mutation, send, enqueue, quota consumption або конкурентне lock acquisition.
- Одночасно дозволено не більше двох зареєстрованих active legacy/new
  mutation/send slots; для solo workflow нормальний стан — одна
  rollout-міграція та максимум одна fully-cut-over міграція, яка очікує
  cleanup. Read-only/shadow flag реєструється, але slot не займає.

---

## 1. Baseline

### 1.1 Git baseline

| Поле | Перевірений стан до створення цього плану |
|---|---|
| Branch | `audit-backend-architecture-2026-07-30` |
| HEAD | `a3bd7bcc007a5700f014a55224ac4eedff63281a` |
| Working tree | `?? TARGET_MODULAR_CLEAN_ARCHITECTURE_DECISION_FINAL.md`; це наданий користувачем ADR, його не змінювати |
| Research baseline | `main` на `e4c1e6721f60c746cb3c3666fb03264859af71cc`, clean |
| Різниця від research | Один commit `a3bd7bc docs(architecture): record full backend audit`; diff додає лише `reports/full_architecture_audit_2026-07-30.md` |
| Production-code drift | Відсутній: `app/`, tests, schema, config і runtime між research baseline та HEAD не змінювалися |

Отже, план будується на тому самому production snapshot, який досліджував
audit. Жодний finding не став неактуальним через post-research code change.

### 1.2 Прочитані нормативні та дослідницькі документи

- `.agent/AGENTS.md`;
- `.agent/core/WORK_SCOPE.md`;
- `.agent/core/DEFINITION_OF_DONE.md`;
- `.agent/core/TASK_OUTPUT_FORMAT.md`;
- `.agent/core/AUTO_CHECKLIST.md`;
- `.agent/core/SECURITY_RULES.md`;
- `.agent/core/GIT_WORKFLOW.md`;
- `.agent/core/PRINCIPLES.md`;
- `.agent/project/PROJECT_CONTEXT.md`;
- `.agent/project/CODE_STYLE.md`;
- `.agent/project/TECH_DEBT_REMEDIATION_PLAN.md`;
- `TARGET_MODULAR_CLEAN_ARCHITECTURE_DECISION_FINAL.md`;
- `reports/full_architecture_audit_2026-07-30.md`;
- початкове завдання з attachment.

### 1.3 Незалежні read-only перевірки

Отримано й самостійно звірено чотири окремі аналізи:

1. security і correctness blockers;
2. module boundaries, transaction ownership і cross-module workflows;
3. Telegram/Celery, inbox/outbox і delivery;
4. tests, rollout, flags, migration registry і cleanup.

Суперечності усунено такими рішеннями:

- refresh rotation використовує атомарний Redis refresh-session state, а не
  вводить SQL-схему без доведеної потреби;
- `outbox_events` лишається audit/manual-review ledger; dispatcher отримує
  окрему таблицю `outgoing_deliveries`;
- Daily push спочатку отримує правильний success-marker і boundary, а durable
  recoverability — лише після готовності Slice 3;
- `architecture_shadow_comparisons` створюється just-in-time з першим R3
  pure-decision shadow, а не як невикористана інфраструктура;
- AR-017 уточнено: walkover Telegram send не є частиною lifecycle mutation
  transaction, але все одно виконується всередині іншої відкритої
  `SessionLocal.begin()` і порушує ADR.

### 1.4 Стан findings на поточному HEAD

| Findings | Статус і опорні точки |
|---|---|
| `AR-001`–`AR-004` | Актуальні: `admin/auth.py::setup_2fa`, `admin/auth_session.py::{refresh_session,logout}`, `admin/deps.py::get_pending_admin`, `services/admin/auth_tokens.py` |
| `AR-005` | Актуальний: `ops_ui/state.py::_LOGIN_FAILED_ATTEMPTS` — process-local |
| `AR-006`–`AR-007` | Актуальні: hidden `bot → workers → bot` cycle; transaction ownership лишається в handlers/workers |
| `AR-008` | Актуальний: failed-flush recovery у `sessions_start_daily.py` і `purchases/service/init.py` використовує aborted session |
| `AR-009`–`AR-010`, `AR-040` | Invariant gaps підтверджені; production incidence для `AR-009/040` не доведена |
| `AR-011`–`AR-017` | Актуальні replay, in-transaction send, pre-commit enqueue, quota/marker і proof-card gaps |
| `AR-018`–`AR-023` | Актуальні: orphan retry primitives, provider-ack crash window, sent/notified-before-send, batch persistence та incoming lease gaps |
| `AR-024`–`AR-028` | Актуальні; refund product harm `AR-027` лишається непідтвердженим, `outbox_events` не є dispatcher |
| `AR-029`–`AR-033` | Актуальні worker/health, analytics truth, queue semantics, global lifecycle і cooldown gaps |
| `AR-034`–`AR-039` | Актуальні concentration, test/guard gaps, docs/duplicate orchestration/config drift |

Немає finding, який можна позначити resolved. Для `AR-017`, `AR-027`,
`AR-031`, `AR-032` і `AR-040` план зберігає audit confidence/уточнення й не
перетворює inference на факт.

---

## 2. Implementation roadmap

Порядок release/slice фіксований:

1. Release 0 — admin security.
2. Release 1 — correctness, analytics truth, Redis state й architecture tooling.
3. Slice 1 — promo reservation expiry.
4. Slice 2 — некритичний Telegram delivery flow.
5. Slice 3 — durable dispatcher, retry, repair і visibility.
6. Referrals.
7. Arena.
8. Friend challenges.
9. Daily Cup і private tournaments.
10. Payments reliability.
11. Подальший cleanup.

Кожна наступна група починається лише після DoD попередньої групи та закриття
її активного dual path. Підготовка pure tests або read-only inventory може
відбуватися паралельно, але production routing не перестрибує цей порядок.

---

## 3. PR-sized milestones

### Release 0 — admin security

#### R0-01 — Safe TOTP enrollment

- **Мета / risk / залежності:** закрити `AR-001`; `R3`; стартовий security
  blocker, незалежний від architecture migration.
- **Файли та зміни:** змінити
  `app/api/routes/admin/auth.py::setup_2fa`,
  `app/services/admin/auth_totp.py::get_totp_setup_payload` і
  `app/services/admin/auth_state.py::{get_totp_secret,set_totp_secret}`;
  first enrollment робити атомарним `SET NX`, existing enrolled secret не
  повертати ніколи. Lost-device recovery/rotation не додавати в цей PR: без
  окремо затвердженої authority/policy safe default — deny.
- **Транзакція / БД / зовнішні ефекти:** owner —
  `auth_totp` service; SQL немає; єдиний effect — коротка Redis operation,
  outage fail-closed як `503`.
- **Тести:** доповнити
  `tests/api/admin/test_admin_auth_session.py` і
  `tests/services/test_admin_auth_totp.py`: first setup, existing secret
  disclosure denied, concurrent setup має одного winner, Redis outage і
  відсутність password-only reset/recovery path.
- **Rollout / rollback / legacy:** direct forward security release без dual
  path; rollback до secret disclosure заборонений, допустимий лише forward fix.
- **DoD / розблоковує:** pending principal не може прочитати наявний secret;
  security regression suite green; розблоковує решту Release 0.

#### R0-02 — Rotating refresh sessions with replay protection

- **Мета / risk / залежності:** закрити `AR-002`; `R3`; залежить від
  `R0-01` лише як release ordering і може готуватися паралельно.
- **Файли та зміни:** додати вузький
  `app/services/admin/auth_refresh_sessions.py`; змінити
  `auth_common.py::AdminTokenPayload`,
  `auth_tokens.py::{build_refresh_token,decode_refresh_token}`,
  `auth.py`, `auth_session.py::refresh_session` і `auth_responses.py`;
  token отримує `jti` та family id, Redis зберігає active successor, atomic
  consume/CAS робить predecessor непридатним і виявляє replay. Initial
  login/2FA success спочатку atomically створює refresh family/session, і лише
  потім будує response та cookies.
- **Транзакція / БД / зовнішні ефекти:** owner — refresh-session service;
  SQL/schema немає; одна Redis Lua/CAS operation; Redis outage fail-closed.
- **Тести:** predecessor replay, два concurrent refresh, revoked/expired
  family, stale successor, Redis outage, cookie replacement і audit-safe
  logging без token contents; initial issuance Redis failure повертає `503`
  без access/refresh cookies, ordering test доводить family-before-cookie.
- **Rollout / rollback / legacy:** legacy refresh tokens без session identity
  відхиляються, користувач один раз login-иться знову; insecure compatibility
  path не створювати.
- **DoD / розблоковує:** лише один successor може бути виданий; replay
  детерміновано revoke-ить family; розблоковує `R0-03` і `R0-04`.

#### R0-03 — Current admin identity, role and enabled authority

- **Мета / risk / залежності:** закрити `AR-004`; `R3`; залежить від `R0-02`
  і preflight `PF-01`.
- **Файли та зміни:** змінити
  `app/api/routes/admin/auth_session.py::refresh_session`,
  `admin/deps.py::get_pending_admin`,
  `admin/auth_helpers.py::configured_admin_role`,
  `app/db/repo/admins_repo.py::{get_by_email,get_or_create}` і, після
  preflight, `app/core/config_admin.py` або `app/db/models/admins.py`;
  stale JWT claims ніколи не оновлюють role в БД, issuance звіряє current
  email/role/enabled authority.
- **Транзакція / БД / зовнішні ефекти:** auth application service є owner;
  коротка current-identity read transaction лише за authoritative values;
  зовнішнього I/O всередині неї немає.
- **Тести:** email/role change invalidates access і refresh; disabled/missing
  identity denied; stale claim не переписує DB; invalid configured role denied.
- **Rollout / rollback / legacy:** coordinated config/schema rollout згідно
  `PF-01`; safe default — deny при відсутності або mismatch, без auto-create з
  claims; rollback не відновлює claim-as-authority.
- **DoD / розблоковує:** кожний token issuance/authorization доводить current
  identity; розблоковує security release verification.

#### R0-04 — Independent logout revocation

- **Мета / risk / залежності:** закрити `AR-003`; `R3`; залежить від `R0-02`.
- **Файли та зміни:** змінити
  `app/api/routes/admin/auth_session.py::logout` і використання
  `auth_tokens.py::revoke_access_token` та
  `auth_refresh_sessions.py::revoke_family`: чинна access-token revocation
  identity/hash і current refresh family/session revoke-яться незалежно,
  cookies очищаються завжди, partial failure повертає `503` і bounded security
  event.
- **Транзакція / БД / зовнішні ефекти:** SQL немає; coordinator виконує дві
  незалежні Redis operations і збирає результат без short-circuit.
- **Тести:** access revoke fails/family revoke succeeds, family fails/access
  succeeds, обидва fail, обидва success, successor refresh unusable after
  logout і cookie clearing у кожному випадку.
- **Rollout / rollback / legacy:** direct release; legacy sequential block
  видалити в тому самому PR після tests; rollback лише до іншої незалежної
  реалізації.
- **DoD / розблоковує:** failure першої revocation не пропускає другу;
  `AR-001`–`AR-004` закриті й Release 0 окремо verified у production;
  розблоковує Release 1.

### Release 1 — correctness, operational truth and tooling

#### R1-01 — Redis-backed Ops login throttle

- **Мета / risk / залежності:** закрити `AR-005`; `R3`; залежить від
  завершеного Release 0.
- **Файли та зміни:** видалити authority
  `app/api/routes/ops_ui/state.py::_LOGIN_FAILED_ATTEMPTS`; розширити чинний
  `app/services/ops_auth.py` atomic increment/TTL/reset; змінити
  `ops_ui/security.py` і `ops_ui/routes.py::login_ops_ui`.
- **Транзакція / БД / зовнішні ефекти:** owner — ops-auth service; SQL немає;
  Redis counter shared між усіма API workers; outage fail-closed `503`.
- **Тести:** два service instances бачать спільний count, threshold race, TTL,
  reset після success, Redis outage; оновити `test_ops_ui*.py` і
  `tests/api/test_ops_auth_unit.py`.
- **Rollout / rollback / legacy:** direct replacement; process-local fallback
  заборонений; rollback можливий лише до іншого shared fail-closed backend.
- **DoD / розблоковує:** throttle не залежить від process topology; розблоковує
  Release 1 gate.

#### R1-02 — Purchase failed-flush recovery

- **Мета / risk / залежності:** закрити purchase half `AR-008`; `R3`; Release 0.
- **Файли та зміни:** змінити
  `app/economy/purchases/service/init.py::init_purchase` і
  `app/db/repo/purchases_repo_writes.py::create`; savepoint має охопити
  локальні purchase-init mutations, включно з promo reservation, а loser
  читає winner лише після rollback savepoint.
- **Транзакція / БД / зовнішні ефекти:** correctness-only PR зберігає чинного
  caller як outer transaction owner; repository не commit-ить; schema й
  зовнішні effects відсутні.
- **Тести:** `test_purchase_init_race_units.py` плюс real PostgreSQL concurrent
  active invoice/same idempotency/promo loser; рівно один purchase, немає orphan
  `RESERVED`, aborted transaction не використовується.
- **Rollout / rollback / legacy:** direct forward-only deploy без module move
  або flag; incident response pauses affected purchase entrypoint і ships a
  forward fix, але не повертає aborted-session behavior.
- **DoD / розблоковує:** conflict loser повертає idempotent winner result у
  валідній transaction; розблоковує Payments stage.

#### R1-03 — Daily start conflict recovery and active-run invariant

- **Мета / risk / залежності:** закрити Daily half `AR-008` і invariant gap
  `AR-009`; `R3`; залежить від data preflight `PF-02`.
- **Файли та зміни:** змінити
  `sessions_start_daily.py::{_create_or_resume_daily_run,start_daily_session}`,
  `DailyRunsRepo`, `app/db/models/daily_runs.py::DailyRun.__table_args__`;
  додати audited
  `scripts/repair_daily_run_duplicates.py::repair_in_progress_daily_runs`;
  додати Alembic revision з partial unique index для одного `IN_PROGRESS`
  `(user_id, berlin_date)` і savepoints для обох conflict sites.
- **Транзакція / БД / зовнішні ефекти:** чинний Daily-start caller лишається
  outer owner у correctness PR. Якщо `PF-02` знаходить duplicates, approved
  manifest обробляється bounded per-user transaction: deterministic survivor
  лишається `IN_PROGRESS`, інші переводяться в approved non-active state без
  delete; після zero-duplicate verification застосовується index. Network I/O
  немає.
- **Тести:** real PostgreSQL two-start concurrency → один run і один active
  `QuizSession`; loser recovery; completed/abandoned semantics; migration
  duplicate-data fixture, repair idempotency і survivor/session references.
- **Rollout / rollback / legacy:** `PF-02` read-only report → separate data/ops
  approval → audited repair transaction → zero-duplicate query → additive
  index. Rollback — forward migration після перевірки даних, не data downgrade.
- **DoD / розблоковує:** concurrency invariant enforce-иться БД і loser не
  читає aborted session; розблоковує Daily-related slices.

#### R1-04 — Cross-platform architecture contracts

- **Мета / risk / залежності:** зробити dependency guard достовірним до pilot;
  `R1`; Release 0.
- **Файли та зміни:** після acceptance fixtures додати pinned `import-linter`
  у `pyproject.toml` і
  `requirements-dev.lock`; створити `.importlinter` та
  `tests/architecture/**`; змінити `scripts/local_ci.sh`,
  `scripts/check_import_cycles.sh`, виправити
  `scripts/check_architecture_debt.py` через `Path.as_posix()` і змінити
  protected `.github/workflows/ci.yml`.
- **Транзакція / БД / зовнішні ефекти:** runtime/DB effects немає; CI dependency
  install only.
- **Тести:** fixtures для relative/local imports, `__init__.py` re-export,
  Windows/Linux path, cycles і forbidden `sqlalchemy/aiogram/fastapi/celery/redis`
  у new domain/application code; regression, що debt guard не vacuously pass-ить
  Windows paths; narrow `windows-latest` architecture job.
- **Rollout / rollback / legacy:** спочатку enforce `app/modules/**` і нові
  workflow edges; legacy violations — ratcheted baseline; existing scripts
  лишаються secondary; protected CI edit потребує окремого review.
- **DoD / розблоковує:** однакові good/bad fixtures pass/fail на Linux і
  Windows; false-pass scripts не є source of truth; розблоковує Slice 1.

#### R1-05 — Migration registry and flag discipline

- **Мета / risk / залежності:** створити контроль тимчасових paths; `R2`;
  залежить від `R1-04`.
- **Файли та зміни:** створити
  `docs/architecture/migration_registry.yaml`,
  `scripts/check_migration_registry.py`,
  `tests/scripts/test_check_migration_registry.py` і lightweight
  `app/core/config_migrations.py`; підключити `MigrationSettingsMixin` до
  `app/core/config.py::Settings`; додати settings та local/CI invocation tests.
- **Транзакція / БД / зовнішні ефекти:** немає runtime mutation; registry
  fields: `flag`, slice/id, owner, tier, legacy/new entrypoints, status/cohort,
  `created_at`, `full_cutover_at`, `review_by`, `observation_ends_at`,
  `removal_condition`, `rollback_command_or_setting`,
  `legacy_usage_metric`, fallback metric, `occupies_write_slot` і append-only
  `review_extensions[{old,new,reason,approved_at,owner}]`.
- **Тести:** orphan flag, expired deadline, third active write slot, code/alias
  mismatch, deleted entrypoint, missing required field і unwired settings fail;
  зміна `review_by` без matching extension amendment fail; інвентаризувати
  `DUELS_ROLLOUT_ENABLED` за actual routing semantics.
- **Rollout / rollback / legacy:** historical inventory може пройти warning
  лише локально під час підготовки цього PR; merged CI hard-fail-ить усі active
  entries без exception. Protected CI edit reviewed окремо.
- **DoD / розблоковує:** до Slice 1 немає warning-only debt; жодний flag не
  існує без owner, dates, legacy metric, rollback і removal condition;
  розблоковує всі flagged slices.

#### R1-06 — Canonical analytics metric contract

- **Мета / risk / залежності:** визначити одну operator truth для `AR-030`;
  `R2`; залежить від `PF-03` і `R1-05`.
- **Файли та зміни:** створити
  `docs/architecture/analytics_metric_contracts.md`; додати immutable
  `user_activity_days(user_id, local_date_berlin)` з unique key і Alembic
  revision; у двох `UsersRepo.touch_last_seen*` paths атомарно upsert-ити цей
  activity-day у тій самій caller transaction. Змінити
  `app/services/analytics_daily.py::build_daily_snapshot`,
  `app/db/repo/analytics_daily_mutations.py::upsert_daily`,
  `AnalyticsRepo` та `analytics_daily`: додати `contract_version`,
  `activity_as_of_utc` і validity marker. Кожний завершений Berlin-day snapshot
  зберігає окремі distinct-user counts: DAU за
  `[day_end-1d, day_end)`, WAU за `[day_end-7d, day_end)`, MAU за
  `[day_end-30d, day_end)`; ці поля не є additive. Upsert інших daily metrics
  не має права переписувати вже valid historical activity fields.
- **Транзакція / БД / зовнішні ефекти:** user-touch caller лишається owner і
  пише `last_seen_at` + activity-day атомарно; analytics aggregation use case є
  owner короткої read/write transaction; без network I/O. Старі snapshots,
  побудовані лише з mutable `User.last_seen_at`, не backfill-яться і не
  позначаються valid.
- **Тести:** framework-free window/definition tests; real PostgreSQL concurrent
  same-user/day upsert, distinct DAU/WAU/MAU windows, DST, day-end boundary,
  late calculation, freshness і “never sum daily rows”; prove old
  `last_seen_at` history is invalid rather than silently reusable.
- **Rollout / rollback / legacy:** additive source/writer deploy, reader ще не
  перемикається. `canonical_valid_from_date` фіксується в registry; historical
  activity backfill дозволений лише з independently proven complete immutable
  source. Safe default — prospective warm-up, old rows
  `activity_source_valid=false`.
- **DoD / розблоковує:** формула, `calculated_at/activity_as_of_utc` і source
  validity відтворювані; є безперервні canonical rows для gate `R1-07`.

#### R1-07 — Analytics reader cutover and orphan-writer retirement

- **Мета / risk / залежності:** завершити `AR-030`; `R2`; `R1-05` і `R1-06`.
- **Файли та зміни:** змінити
  `admin/overview_activity_metrics.py::count_distinct_users`,
  `overview_payload_kpis.py` і додати
  `AnalyticsRepo.get_activity_snapshot_at_or_before(as_of_utc)` для canonical
  `analytics_daily`; вимкнути beat registration у
  `workers/tasks/admin_daily_metrics.py`, не видаляючи ще `daily_metrics`.
- **Транзакція / БД / зовнішні ефекти:** read query contract owner; deprecated
  writer перестає mutating; schema additive/unchanged.
- **Тести:** reader обирає latest completed Berlin-day snapshot at/before
  `as_of_utc`, ніколи не sum-ить daily DAU/WAU/MAU rows; current/previous KPI
  беруть відповідні snapshot endpoints і повертають explicit
  `activity_as_of_utc`; admin/internal values, bounded reconciliation,
  invalid/missing/stale snapshot і schedule absence. Окремий gate-test доводить
  valid current/previous endpoints для всіх `7d/30d/90d` dashboard periods.
- **Rollout / rollback / legacy:** explicit reader flag у registry; internal
  admin → full cutover лише після source-valid horizon. Без approved immutable
  backfill safe default — prospective warm-up **120 completed Berlin days**
  (90-day previous endpoint + its 30-day MAU window); до цього legacy reader
  лишається authoritative. Rollback повертає reader, deprecated table
  лишається; routing cleanup після ≥7 stable days у `R1-10`, schema cleanup у
  `C-07`.
- **DoD / розблоковує:** dashboard і internal analytics мають одну source of
  truth, deprecated writer не запускається; розблоковує Release 1 exit.

#### R1-08 — Truthful queue and webhook health semantics

- **Мета / risk / залежності:** закрити `AR-031`; `R2`; Release 0.
- **Файли та зміни:** змінити
  `app/api/routes/admin/system.py::{_service_status,get_system_health}`:
  `LLEN celery` не називати failed/DLQ, повертати
  `failed_queue_configured=false`/`failed=null`; створити
  `app/infrastructure/telegram/webhook_readiness.py::get_webhook_readiness`
  з bounded `getWebhookInfo` probe. `processed_updates_15m` лишається activity,
  не readiness signal.
- **Транзакція / БД / зовнішні ефекти:** DB/Redis/Celery reads завершуються
  окремо; Telegram readiness probe виконується з timeout поза SQL transaction,
  перевіряє registered HTTPS webhook path, provider error/pending metadata;
  probe failure повертає `state=unknown`, не fake healthy.
- **Тести:** оновити `tests/api/admin/test_admin_system.py`: zero traffic не
  змінює independent ready result; absent/wrong webhook або recent provider
  error degraded, probe timeout unknown; only configured queues count, missing
  DLQ не masquerade-ить zero, dependency failures окремі від activity.
- **Rollout / rollback / legacy:** coordinated admin API contract release,
  schema/flag не потрібні; rollback git revert.
- **DoD / розблоковує:** кожне поле має правдиву operational definition;
  розблоковує later delivery dashboard.

#### R1-09 — Shared bounded Daily Cup UI cooldown

- **Мета / risk / залежності:** закрити `AR-033`; `R2`; `R1-05`.
- **Файли та зміни:** замінити
  `daily_cup_menu_flow.py::_last_opened_at_by_user_id` і `_is_menu_spam` на
  narrowly named Redis cooldown service; atomic Lua
  `touch_and_check(key, ttl=2s)` спочатку перевіряє existence, потім завжди
  `SET EX`, тому blocked click refresh-ить sliding window. Key використовує
  `callback.from_user.id` (`telegram_user_id`) і викликається до SQL
  transaction.
- **Транзакція / БД / зовнішні ефекти:** Redis adapter owner для cooldown;
  Redis I/O не входить у `SessionLocal.begin()`; outage fail-open із bounded
  warning, бо це UI spam guard, не security control.
- **Тести:** `tests/bot/test_daily_cup_menu_flow.py`: shared instances, TTL,
  blocked click refreshes TTL, Telegram-id key, bounded key lifetime, outage і
  ordering before DB transaction.
- **Rollout / rollback / legacy:** direct reversible replacement без parallel
  implementation/flag; rollback git/config revert у межах observation, старий
  process-local dict видаляється в цьому PR після characterization.
- **DoD / розблоковує:** semantics однакові між processes і memory не росте;
  розблоковує `R1-10`.

#### R1-10 — Analytics reader route cleanup and Release 1 exit

- **Мета / risk / залежності:** закрити тимчасовий read-only analytics route та
  Release 1 join до pilot; `R2`; completion/evidence всіх `R1-01`–`R1-09`,
  включно з `R1-07` full cutover ≥7 stable days.
- **Файли та зміни:** видалити legacy reader branch, analytics reader flag,
  obsolete reconciliation-only route tests і registry entry; не видаляти
  `daily_metrics` table/model — це окремий `C-07`.
- **Транзакція / БД / зовнішні ефекти:** canonical analytics query є єдиним
  reader; deprecated writer лишається disabled; schema/network effects немає.
- **Тести:** zero legacy-reader call/import, canonical overview regression,
  stale/fresh response, settings та registry validator.
- **Rollout / rollback / legacy:** forward fix після observation; відновлення
  reader потребує нового registered change, але schema ще доступна для forensic
  read.
- **DoD / розблоковує:** Release 1 не лишає active route flag чи warning-only
  registry entry; розблоковує `S1-01`.

### Slice 1 — promo reservation expiry pilot

#### S1-01 — ExpirePromoReservations vertical slice

- **Мета / risk / залежності:** довести мінімальний module UoW pattern на
  `AR-007`; `R1`; усі Release 0/1 milestones завершені.
- **Файли та зміни:** створити
  `app/modules/economy/promo/application/expire_reservations.py` і
  `app/modules/economy/promo/adapters/sqlalchemy_uow.py`; змінити
  `app/workers/tasks/promo_maintenance.py::run_promo_reservation_expiry_async`
  на thin entrypoint; адаптер використовує чинний
  `PromoRepo.expire_reserved_redemptions`.
- **Транзакція / БД / зовнішні ефекти:** `ExpirePromoReservations` owns
  `PromoUnitOfWork`; одна UPDATE transaction `RESERVED → EXPIRED`; network,
  broker і schema effects відсутні.
- **Тести:** characterization current counts; framework-free application test;
  один real PostgreSQL happy path/rollback; thin Celery task wiring; чинні
  worker tests.
- **Rollout / rollback / legacy:** direct route replacement, без flag і shadow;
  rollback task import/git revert; old worker orchestration видалити після
  equivalence у тому самому PR.
- **DoD / розблоковує:** task не імпортує `SessionLocal`, ORM чи policy; expired
  rows/counts еквівалентні; pause gate — якщо complexity не зменшилася,
  roadmap зупинити; успіх розблоковує Slice 2.

### Slice 2 — noncritical Telegram flow

#### S2-01 — Daily push success-marker correctness

- **Мета / risk / залежності:** окремо виправити `AR-020` ordering до
  architecture move; `R2`; `S1-01`.
- **Файли та зміни:** змінити
  `app/workers/tasks/daily_challenge_async.py::run_daily_push_notifications_async`
  та `DailyPushLogsRepo.create_once`: eligibility перевіряти до send, а
  success-marker створювати лише після успішного `bot.send_message`;
  stable key `daily_push:{local_date}:{kind}:{user_id}`.
- **Транзакція / БД / зовнішні ефекти:** short read transaction → Telegram
  send без transaction → short success-record transaction; provider-success
  crash може дати duplicate, але не suppress-ить unsent message.
- **Тести:** characterization recipient/kind behavior; send failure leaves
  eligible; success marks once; provider-success/before-marker crash documented;
  no SQL transaction open during send.
- **Rollout / rollback / legacy:** direct correctness release без flag; rollback
  до pre-send marker заборонений, лише forward fix.
- **DoD / розблоковує:** failed send не стає durably ineligible; розблоковує
  boundary extraction `S2-02`.

#### S2-02 — Daily push application boundary and presenter

- **Мета / risk / залежності:** довести noncritical Telegram boundary без
  generic dispatcher; `R2`; `S2-01`.
- **Файли та зміни:** створити
  `app/modules/gameplay/daily_push/application/prepare_daily_push.py`,
  SQL adapter і immutable recipient/payload DTO; Telegram presenter лишити в
  adapter/entrypoint; зробити `daily_challenge.py`/`daily_challenge_async.py`
  thin; application не імпортує bot texts/keyboards/Celery.
- **Транзакція / БД / зовнішні ефекти:** application use case owns target/read
  і result-record UoWs; presenter sends між ними після commit; no broker/network
  in transaction.
- **Тести:** application selection/DTO tests, SQL adapter integration,
  presenter contract, real Celery entrypoint test, import contract.
- **Rollout / rollback / legacy:** direct equivalent replacement без parallel
  write path; rollback git revert; legacy split code видалити після green
  equivalence, `daily_push_logs` поки лишити.
- **DoD / розблоковує:** task/presenter не володіє policy або SQL transaction;
  stable payload/key готові до durable routing; розблоковує Slice 3.

### Slice 3 — durable outgoing delivery foundation

#### D3-01 — Additive outgoing-delivery schema

- **Мета / risk / залежності:** створити messaging-owned durable source of
  truth; `R3`; `S2-02`, `R1-04`, `R1-05`, preflight `PF-06`.
- **Файли та зміни:** створити
  `app/modules/messaging/domain/outgoing_delivery.py`,
  `app/modules/messaging/public/outgoing_effects.py::{OutgoingEffect,OutgoingEffectWriterPort}`,
  `app/modules/messaging/adapters/sqlalchemy/models.py`,
  `app/modules/messaging/adapters/sqlalchemy/outgoing_effect_writer.py`,
  `app/bootstrap/outgoing_effect_writer.py::SessionBoundOutgoingEffectWriterFactory`,
  repository adapter і next generated Alembic revision для
  `outgoing_deliveries`; не змінювати semantics `outbox_events` або
  `telegram_delivery_attempts`.
- **Транзакція / БД / зовнішні ефекти:** producers ще disabled; table містить
  closed `dispatch_kind=TELEGRAM|INTERNAL_HANDLER`,
  effect/aggregate/recipient, payload type/version, validated bounded payload,
  unique `idempotency_key`, states
  `PENDING/CLAIMED/RETRY/SENT/FAILED/SKIPPED`, attempts, claim token/lease,
  retry, provider id, bounded error і replay audit fields.
  `OutgoingEffectWriterPort.put_once` використовує caller-owned SQLAlchemy
  session, не begin/commit/rollback-ить; same key/same canonical payload
  повертає existing row, same key/different digest дає `IdempotencyConflict`.
  Bootstrap factory має `for_session(session) -> OutgoingEffectWriterPort` і
  inject-иться в source UoW factory; лише bootstrap imports concrete messaging
  adapter.
- **Тести:** migration/metadata/constraints; partial indexes для due
  `PENDING/RETRY` і expired `CLAIMED`; unique idempotency race на PostgreSQL;
  payload privacy/version validation; source rollback прибирає outgoing row;
  writer не володіє transaction. Architecture contract дозволяє лише
  `source.application|workflow → messaging.public`, але забороняє source
  imports messaging adapters/domain/ORM/repository.
- **Rollout / rollback / legacy:** additive deploy, жодний producer/consumer не
  ввімкнений; rollback лишає table unused, downgrade не потрібен.
- **DoD / розблоковує:** schema відповідає ADR і не претендує на exactly-once;
  розблоковує `D3-02`.

#### D3-02 — Claim, lease, CAS and retry state machine

- **Мета / risk / залежності:** реалізувати recoverable concurrency protocol;
  `R3`; `D3-01`.
- **Файли та зміни:** створити
  `app/modules/messaging/application/outgoing_delivery.py`,
  use-case-specific ports і SQL adapter operations `claim_due`,
  `mark_sent`, `schedule_retry`, `mark_failed`, `mark_skipped`,
  `reclaim_expired`.
- **Транзакція / БД / зовнішні ефекти:** кожний claim/outcome — окрема коротка
  application-owned transaction; claim використовує
  `FOR UPDATE SKIP LOCKED`, random token, lease й attempt++; outcome CAS —
  `id/status/token`; зовнішнього I/O немає.
- **Тести:** два workers не claim-ять один row; stale reclaim; старий token не
  завершує новий claim; retry due ordering, max attempts/age, idempotency race,
  rollback після exception — real PostgreSQL.
- **Rollout / rollback / legacy:** disabled code path; additive rollback;
  rows не видаляти.
- **DoD / розблоковує:** усі legal/illegal transitions явні й CAS-protected;
  розблоковує provider adapter, replay і runtime.

#### D3-03 — Telegram delivery adapter and crash-window contract

- **Мета / risk / залежності:** виконувати provider effect поза transaction;
  `R3`; `D3-02`.
- **Файли та зміни:** створити
  `app/modules/messaging/application/delivery_ports.py`,
  `app/modules/messaging/adapters/telegram/outgoing_sender.py` і explicit
  closed `PayloadPresenterMap` allowlist без runtime registration; adapter не
  імпортує handlers, keyboards,
  `app.bot.application` або workers.
- **Транзакція / БД / зовнішні ефекти:** claim commit → Telegram send → CAS
  outcome commit; classify `RetryAfter`, blocked/terminal і generic retry;
  bounded exponential backoff+jitter; store provider message id when available.
- **Тести:** failure windows after claim/before send, provider failure, provider
  success/before `SENT`, retry-write failure; duplicate message у provider-ack
  window дозволений і observable, duplicate business mutation — ні.
- **Rollout / rollback / legacy:** adapter disabled until `D3-06`; rollback не
  торкається rows.
- **DoD / розблоковує:** no network I/O in SQL transaction; explicit
  at-least-once contract; розблоковує `D3-04`.

#### D3-04 — `q_delivery` dispatcher and stale repair

- **Мета / risk / залежності:** дати durable rows реального consumer/repair;
  `R3`; `D3-02`, `D3-03`, preflight `PF-05`.
- **Файли та зміни:** створити thin tasks
  `dispatch_outgoing_row(row_id)` і
  `scan_due_outgoing_delivery(batch_limit=50)`,
  compile-time `app/bootstrap/outgoing_effect_handlers.py`; змінити
  `app/workers/celery_app.py`, `Makefile`, `docker-compose.prod.yml` і
  `deploy/quiz-arena/docker-compose.prod.yml` для `q_delivery`.
- **Транзакція / БД / зовнішні ефекти:** scanner кожні 5 секунд бере
  single-run advisory guard, у short transaction читає ≤50 ids, enqueue робить
  після commit; immediate post-commit wakeup — best-effort latency optimization;
  worker слухає `q_delivery,q_high,q_normal,q_low`, prefetch `1`, без п’ятого
  process.
- **Тести:** Celery route/schedule, missed immediate enqueue recovered scanner,
  expired lease, scanner overlap, unknown effect terminal classification,
  explicit internal-handler idempotency, worker-lost/task limit behavior;
  PostgreSQL repair integration.
- **Rollout / rollback / legacy:** tasks і queue deploy-яться disabled; protected
  runtime files потребують окремого approval/review. До першого producer tasks
  можна disable; після producer activation routing rollback зупиняє лише нові
  rows, а consumer/repair продовжує drain pending; table не drop-иться.
- **DoD / розблоковує:** production topology може claim/recover без orphan
  primitive; розблоковує `D3-05/06`, але не production activation.

#### D3-05 — Audited same-row replay and suppress

- **Мета / risk / залежності:** безпечна operator recovery; `R3`; `D3-02`.
- **Файли та зміни:** додати application commands `ReplayOutgoingDelivery` і
  `SuppressOutgoingDelivery`; audited CAS
  `FAILED|SKIPPED → RETRY` на тому самому row; payload та
  `idempotency_key` immutable; suppress дозволяє лише
  `PENDING|RETRY|FAILED → SKIPPED` з reason, але відхиляє active `CLAIMED`;
  clone endpoint відсутній.
- **Транзакція / БД / зовнішні ефекти:** command owns one short CAS
  transaction; wakeup enqueue тільки після commit і його failure не скасовує
  replay.
- **Тести:** concurrent replay має одного winner; replay для `SENT/CLAIMED`
  rejected; suppress transition/state race, same row/key retained;
  operator/reason/time audit; source business mutation не повторюється.
- **Rollout / rollback / legacy:** command не exposed до `D3-06`; rollback
  лишає audit/state intact.
- **DoD / розблоковує:** manual repair не може clone-ити effect; розблоковує
  admin surface.

#### D3-06 — Admin visibility, metrics and alerts

- **Мета / risk / залежності:** visibility має ship разом із dispatcher;
  `R3`; `D3-04`, `D3-05`, Release 0.
- **Файли та зміни:** створити
  `app/api/routes/admin/delivery.py`,
  messaging query adapter і
  `app/workers/tasks/outgoing_delivery_observability.py`; include route;
  змінити `admin/system.py` для `q_delivery` і PostgreSQL failed truth.
- **Транзакція / БД / зовнішні ефекти:** list/detail read-only; replay/suppress
  application-owned transaction, safe default `super_admin`; ops alert
  виконується після DB read transaction.
- **Тести:** admin auth/audit, list/detail/state age, replay/suppress, counts,
  oldest due, stale claims, attempts, throughput/failure, bounded error class;
  alerts: critical due >30s і backlog >100 for 5m; p95 claim target <5s.
- **Rollout / rollback / legacy:** deploy before activation; PostgreSQL є source
  of truth, Redis `LLEN q_delivery` лише transport backlog; rollback UI не
  вимикає consumer для pending rows.
- **DoD / розблоковує:** on-call бачить і ремонтує stuck/failed work;
  `D3-03/04/05/06` мають бути одним production release gate; розблоковує pilot.

#### D3-07 — Durable Daily push cutover

- **Мета / risk / залежності:** перший recoverable end-to-end flow; `R2`;
  `D3-01`–`D3-06`, `S2-02`, preflights `PF-04`–`PF-07`.
- **Файли та зміни:** daily push application transaction викликає injected
  `OutgoingEffectWriterPort.put_once` зі stable key замість direct send;
  presenter type versioned; додати explicit routing flag і registry entry;
  legacy/new routes взаємовиключні.
- **Транзакція / БД / зовнішні ефекти:** source use case owns transaction;
  concrete messaging writer прив’язаний composition root-ом до тієї самої
  SQLAlchemy session, але не володіє transaction; immediate wakeup після
  commit; dispatcher sends. Selectors тимчасово враховують legacy success log
  і outgoing key, але dual-send/dual-write заборонені.
- **Тести:** source commit/enqueue failure, dispatcher retry/replay,
  route exclusivity, rollback duplicate bridge, real entrypoint integration,
  recipient/payload digest shadow only.
- **Rollout / rollback / legacy:** internal/admin recipients → deterministic
  cohort → full; rollback flag stops only new producers, dispatcher продовжує
  drain every existing nonterminal row.
- **DoD / розблоковує:** real consumer, stale repair, operator visibility і
  recoverable pilot працюють; розблоковує `D3-08` після 7-day observation.

#### D3-08 — Pilot legacy-path cleanup

- **Мета / risk / залежності:** закрити першу dual path; `R2`; `D3-07`, ≥7
  stable full-cutover days, zero unexpected fallback.
- **Файли та зміни:** видалити direct Daily push sender routing, flag/config,
  obsolete tests і registry entry; `daily_push_logs` лишити read-only до
  schema cleanup, якщо ще є reader.
- **Транзакція / БД / зовнішні ефекти:** нових effects немає; dispatcher
  продовжує processing existing rows.
- **Тести:** no legacy imports/routes/flag, dispatcher regression, registry
  validator, pending-row drain.
- **Rollout / rollback / legacy:** rollback PR не resurrect-ить direct sender,
  доки nonterminal durable rows існують; відновлення routing потребує нового
  registered entry.
- **DoD / розблоковує:** Slice 3 має zero unmanaged legacy path; major pause
  gate — roadmap може завершитися тут; інакше розблоковує Referrals.

### Referrals

#### REF-01 — Referral qualification application use case

- **Мета / risk / залежності:** перенести qualification ownership без delivery
  change; `R2`; `D3-08`.
- **Файли та зміни:** створити
  `app/modules/economy/referrals/application/qualify_referrals.py` і
  module UoW adapter; перенести orchestration з
  `app/economy/referrals/service/qualification.py` та зробити
  `workers/tasks/referrals.py::run_referral_qualification_checks_async` thin.
- **Транзакція / БД / зовнішні ефекти:** economy use case owns locks,
  idempotency і one transaction; notification не впливає на qualification;
  external effects відсутні.
- **Тести:** characterization qualification/rejection, application policy,
  PostgreSQL locking/idempotency, thin Celery entrypoint.
- **Rollout / rollback / legacy:** direct behavior-equivalent replacement без
  parallel writer/flag; якщо equivalence не доведено, milestone блокується, а
  не відкриває третій slot; ≥7 days перед separate old-service cleanup.
- **DoD / розблоковує:** worker не володіє transaction/policy; failed
  notification не змінює reward correctness; розблоковує `REF-02`.

#### REF-02 — Referral reward choice and grant

- **Мета / risk / залежності:** isolate reward mutation і preserve ledger/
  entitlement invariants; `R3`; `REF-01`.
- **Файли та зміни:** створити application commands для reward choice/grant;
  адаптувати `rewards_distribution.py`, `rewards_grant.py` і bot choice handler;
  public DTO замість ORM/handler objects.
- **Транзакція / БД / зовнішні ефекти:** economy module UoW owns referral state,
  purchase/entitlement/ledger idempotency в одному commit; Telegram не входить;
  cross-module workflow не потрібний.
- **Тести:** replay choice, concurrent grant, entitlement+ledger atomicity,
  rollback at each mutation, real PostgreSQL; pure reward decision shadow with
  zero mismatch.
- **Rollout / rollback / legacy:** flagged internal/cohort/full; additive
  routing, legacy observation ≥14 days + referral cycle.
- **DoD / розблоковує:** reward не дублюється й не залежить від send outcome;
  розблоковує durable notification.

#### REF-03 — Durable referral reward notification

- **Мета / risk / залежності:** закрити `AR-023`; `R3`; `REF-02`, Slice 3.
- **Файли та зміни:** reward transaction через injected
  `OutgoingEffectWriterPort.put_once` записує versioned
  `referral.reward_ready.v1` outgoing row; змінити
  `rewards_distribution.py`, `referrals_notifications.py` і
  `workers/tasks/referrals.py`; `notified_at` більше не є pre-send terminal
  marker.
- **Транзакція / БД / зовнішні ефекти:** economy source use case owns
  transaction; session-bound messaging writer не commit-ить, тому mutation +
  durable row atomic; dispatcher sends after commit; notification delivery
  state є authority.
- **Тести:** commit/wakeup failure, provider failure/retry, replay same row,
  reward grant once, no `notified_at` on unsent, operator visibility.
- **Rollout / rollback / legacy:** registered flag, internal/cohort/full;
  rollback stops new rows but drains pending; no dual-send.
- **DoD / розблоковує:** provider failure не приховує granted reward;
  розблоковує observation/cleanup.

#### REF-04 — Referral cutover cleanup

- **Мета / risk / залежності:** закрити referral dual paths; `R3`; `REF-02` і
  `REF-03` full cutover, ≥14 stable days від пізнішого cutover та один complete
  referral/reward cycle.
- **Файли та зміни:** видалити legacy qualification/reward routing, raw
  notification sender, pre-send `notified_at` selection semantics, flag,
  obsolete tests і registry entry.
- **Транзакція / БД / зовнішні ефекти:** only new economy UoW + dispatcher;
  schema column видаляти пізніше лише якщо zero readers.
- **Тести:** no legacy caller/import, full referral/replay integration,
  migration registry/architecture guard.
- **Rollout / rollback / legacy:** rollback через new-path fix; pending rows
  зберігаються; destructive column change не входить.
- **DoD / розблоковує:** один business path, zero fallback; розблоковує Arena.

### Arena

#### A-01 — Complete terminal replay result

- **Мета / risk / залежності:** окремо закрити `AR-011` до migration; `R3`;
  `REF-04`.
- **Файли та зміни:** виправити
  `service_challenger_complete.py::_complete_arena_challenger_context`,
  `ArenaAttemptCompletionResult` і
  `arena_duel_flow_results.py::send_arena_completion_result`: replay load-ить
  complete `completed_attempt/opponent_attempt` і рендерить terminal result.
- **Транзакція / БД / зовнішні ефекти:** чинний caller owns read transaction;
  mutation/send semantics не змінюються в цьому PR.
- **Тести:** current completion vs replay DTO/render equivalence, win/draw/loss,
  expired duel; explicit bug-fix characterization.
- **Rollout / rollback / legacy:** direct fix без flag; rollback до silent
  terminal response заборонений.
- **DoD / розблоковує:** replay повертає повний immutable result; розблоковує
  shadow/application extraction.

#### A-02 — Arena completion application path and shadow evidence

- **Мета / risk / залежності:** відокремити pure scoring/result і transaction
  owner; `R3`; `A-01`, `R1-05`.
- **Файли та зміни:** створити
  `app/modules/competitions/arena/application/complete_attempt.py`, domain DTO/
  policy й SQL UoW; just-in-time створити
  `app/db/models/architecture_shadow_comparisons.py`, scoped repository,
  Alembic revision і 30-day retention wiring.
- **Транзакція / БД / зовнішні ефекти:** new application path disabled для
  writes; pure legacy/new decision виконується без duplicate locks/mutations,
  canonical digests пишуться окремо; no raw PII/payload.
- **Тести:** scorer/result characterization, application/UoW PostgreSQL tests,
  canonical digest, bounded difference enum, retention, zero-mismatch threshold.
- **Rollout / rollback / legacy:** shadow only, minimum sample/business cycle з
  `PF-07`; no routing cutover; rollback disables comparison writer.
- **DoD / розблоковує:** pure decisions match або approved bug difference
  documented; evidence queryable; розблоковує `A-03`.

#### A-03 — CreateArenaDuelWithAccess workflow

- **Мета / risk / залежності:** атомарно створити Arena duel, baseline attempt,
  playable session і authorized access без global UoW; `R3`; `A-02`.
- **Файли та зміни:** створити
  `app/workflows/create_arena_duel_with_access/`; змінити
  `limits_service_api.py`, `limits_resolvers.py` і
  `arena_duels/service_baseline_start.py`; ports:
  `EconomyDuelAccessPort`, `ArenaCreationPort`,
  `GameplaySessionStartPort`.
- **Транзакція / БД / зовнішні ефекти:** workflow owns one SQL transaction;
  user lock → access read/reserve → duel/attempt/session create; ports можуть
  share одну session, але не commit-ять; no Telegram/Redis/Celery.
- **Тести:** concurrent create at free/premium/credited-ticket boundaries,
  idempotent attempt/session, lock order і rollback leaves neither access
  consumption nor duel; максимум три modules/import allowlist.
- **Rollout / rollback / legacy:** зареєструвати один staged write slot
  `ARENA_ACCESS_MIGRATION_STAGE`; pure decision shadow, потім
  `LEGACY → CREATE_NEW` для internal/cohort; routes mutually exclusive.
- **DoD / розблоковує:** create path не лишає partial access/duel state і має
  zero invariant mismatch; розблоковує `A-04`.

#### A-04 — AcceptArenaDuelWithAccess workflow

- **Мета / risk / залежності:** атомарно accept-нути duel, створити challenger
  attempt/session і перевірити access capacity; `R3`; `A-03`.
- **Файли та зміни:** створити
  `app/workflows/accept_arena_duel_with_access/`; змінити
  `arena_duels/accept.py` і accept-specific limit resolver; ports:
  `EconomyDuelAccessPort`, `ArenaAcceptancePort`,
  `GameplaySessionStartPort`.
- **Транзакція / БД / зовнішні ефекти:** workflow owns one transaction та
  documented user/duel lock order; no provider/broker effect.
- **Тести:** two challengers race, replay, expired/already-accepted duel,
  insufficient capacity, rollback and no fourth-module/workflow chaining.
- **Rollout / rollback / legacy:** той самий staged access slot переходить
  `CREATE_NEW → CREATE_ACCEPT_NEW`; create лишається new, accept має exactly one
  selected route; R3 observation.
- **DoD / розблоковує:** accepted duel завжди має рівно один authorized playable
  challenger attempt; розблоковує `A-05`.

#### A-05 — CreateFriendChallengeWithAccess for Arena revanche

- **Мета / risk / залежності:** винести вже атомарне revanche challenge/access
  створення у спільний bounded workflow до Friend stage; `R3`; `A-04`.
- **Файли та зміни:** створити
  `app/workflows/create_friend_challenge_with_access/` і competitions public
  command/DTO; змінити
  `arena_duels/service.py::create_friend_challenge_from_arena_duel` та
  `arena_duels/revanche.py::prepare_arena_revanche_request`; immutable question
  ids приходять з Arena context. Regular Friend handlers ще не мігрують.
- **Транзакція / БД / зовнішні ефекти:** workflow owns competition
  challenge/cap + economy entitlement/ticket transaction through narrow ports;
  no workflow chaining, transport or generic duel service.
- **Тести:** concurrent/replayed revanche, cap/ticket/premium variants, source
  attempt binding, rollback, same DTO as current path; regular Friend routes
  unchanged.
- **Rollout / rollback / legacy:** access slot переходить
  `CREATE_ACCEPT_NEW → ALL_NEW`; staged enum є одним slot, не трьома flags;
  full Arena access observation починається тут.
- **DoD / розблоковує:** Arena revanche creation використовує shared command,
  але не залежить від майбутнього Friend runtime cutover; розблоковує `A-06`.

#### A-06 — Arena completion application cutover

- **Мета / risk / залежності:** перемкнути completion mutation і result delivery
  на перевірений application UoW; `R3`; `A-02`, `A-05`, Slice 3.
- **Файли та зміни:** route
  `play_flow_arena_completion.py` через
  `app/modules/competitions/arena/application/complete_attempt.py`; через
  injected `OutgoingEffectWriterPort.put_once` створювати versioned
  `arena.result_ready.v1` effect; presenter залишається adapter.
- **Транзакція / БД / зовнішні ефекти:** competition use case owns state +
  session-bound durable effect transaction; messaging writer не commit-ить;
  dispatcher/Telegram after commit. Economy reward у current Arena completion
  відсутній, тому workflow не створюється.
- **Тести:** state/effect atomicity, commit/wakeup failure, replay result,
  provider retry, same-key conflict, source rollback і real aiogram entrypoint.
- **Rollout / rollback / legacy:** відкрити другий staged slot
  `ARENA_DELIVERY_MIGRATION_STAGE=LEGACY → RESULT_NEW`; internal/cohort/full,
  pending rows always drain.
- **DoD / розблоковує:** completion path не await-ить worker і durable result не
  губиться після commit; розблоковує `A-07`.

#### A-07 — Arena beaten-notification delivery

- **Мета / risk / залежності:** закрити best-effort beaten gap `AR-012` без
  зміни completion state; `R3`; `A-06`.
- **Файли та зміни:** замінити
  `play_flow_arena_completion.py::_send_arena_beaten_notification_best_effort`
  і `arena_duels_notification_delivery.py` на explicit
  `arena.beaten.v1` outgoing effect через public writer port.
- **Транзакція / БД / зовнішні ефекти:** completion UoW додає beaten effect
  лише для eligible opponent у source transaction; Telegram тільки dispatcher
  post-commit.
- **Тести:** winner/loser/no-op eligibility, provider failure/replay, source
  mutation once, provider-ack duplicate observable, no network/advisory-lock
  overlap.
- **Rollout / rollback / legacy:** delivery stage переходить
  `RESULT_NEW → RESULT_BEATEN_NEW`; exactly one sender per effect; ≥14-day
  observation не скидається для already-full result path.
- **DoD / розблоковує:** beaten notification recoverable і не впливає на
  terminal result; розблоковує `A-08`.

#### A-08 — Arena revanche durable delivery and quota outcome

- **Мета / risk / залежності:** закрити `AR-013` і analytics-as-authority для
  revanche; `R3`; `A-05`, `A-07`, preflight `PF-11`.
- **Файли та зміни:** змінити
  `arena_revanche_delivery.py`, `revanche_delivery_guard.py` і
  `arena_revanche_flow.py`: shared workflow створює challenge та через
  `OutgoingEffectWriterPort.put_once` — `arena.revanche_invite.v1`; analytics
  event лишається observation, не delivery/quota authority.
- **Транзакція / БД / зовнішні ефекти:** workflow owns challenge/access +
  outgoing row in one transaction; Telegram after commit; failed send не
  видаляє challenge й не ставить terminal delivered quota marker.
- **Тести:** concurrent click/replay, one challenge/row, provider terminal/
  retry/crash windows, same-row operator replay, quota policy from `PF-11`,
  sender/receiver entrypoints.
- **Rollout / rollback / legacy:** delivery stage переходить
  `RESULT_BEATEN_NEW → ALL_NEW`; rollback зупиняє new producers, але dispatcher
  drains pending; complete Arena/revanche business cycle.
- **DoD / розблоковує:** challenge і invitation мають незалежні, видимі
  outcomes без pre-send sent marker; розблоковує `A-09`.

#### A-09 — Arena staged-path cleanup

- **Мета / risk / залежності:** закрити обидва Arena write slots; `R3`; `A-05`
  access і `A-08` delivery full cutover ≥14 stable days + complete Arena cycle.
- **Файли та зміни:** видалити legacy branches із
  `arena_duels/service_baseline_start.py`, `arena_duels/accept.py`,
  `play_flow_arena_completion.py`, `arena_duels_notification_delivery.py` і
  `arena_revanche_delivery.py`; видалити direct worker await/send, analytics
  authority, `ARENA_ACCESS_MIGRATION_STAGE`,
  `ARENA_DELIVERY_MIGRATION_STAGE`, obsolete tests і обидва registry entries;
  ratchet architecture contract.
- **Транзакція / БД / зовнішні ефекти:** only three bounded workflows,
  competition UoW, public writer port and dispatcher; destructive schema
  cleanup deferred.
- **Тести:** full create/accept/complete/replay/revanche integration, zero
  legacy usage/import/fallback, registry/settings guards, pending-row drain.
- **Rollout / rollback / legacy:** forward fix only; durable pending retained;
  відновлення legacy потребує нового decision/registry entry.
- **DoD / розблоковує:** Arena не займає rollout slots і має один route per
  command/effect; розблоковує Friend challenges.

### Friend challenges

#### F-01 — Serialize friend cap checks

- **Мета / risk / залежності:** закрити `AR-010` окремим correctness PR; `R3`;
  `A-09`.
- **Файли та зміни:** змінити
  `friend_challenges_create.py::create_friend_challenge` і
  `duels/limits_resolvers.py::resolve_friend_create_access_type`: lock creator
  first, потім live/open/daily cap, access capacity й insert у тій самій
  transaction.
- **Транзакція / БД / зовнішні ефекти:** чинний caller owns one PostgreSQL
  transaction; no broker/network; advisory/user row lock key documented.
- **Тести:** real PostgreSQL concurrent creates at each boundary, loser result,
  rollback, no cap exceed.
- **Rollout / rollback / legacy:** direct correctness fix; no architecture move
  або flag.
- **DoD / розблоковує:** DB-observable cap serializable; розблоковує unified
  workflow.

#### F-02 — Adopt CreateFriendChallengeWithAccess for regular entrypoints

- **Мета / risk / залежності:** прибрати duplicate orchestration `AR-038` і
  зберегти access invariant без нового workflow; `R3`; `F-01`, `A-05`.
- **Файли та зміни:** додати direct/open source handling до existing
  `app/workflows/create_friend_challenge_with_access/`; створити
  competitions application command/DTO і `GameplayQuestionPlanPort`; звести
  `friend_lobby_flow.py` та `friend_challenge_flow.py` до одного command.
- **Транзакція / БД / зовнішні ефекти:** workflow coordinates competitions
  cap/create, economy access і gameplay question plan through максимум три
  ports under one user lock; no transport/workflow chaining.
- **Тести:** both regular entrypoints same DTO/outcome, free/premium/ticket,
  question-plan/revanche variants, concurrency/idempotency, rollback і boundary
  guard.
- **Rollout / rollback / legacy:** відкрити
  `FRIEND_ACCESS_MIGRATION_STAGE=LEGACY → REGULAR_NEW`; pure decision shadow,
  internal/cohort/full, zero mismatch; Arena revanche route лишається stable.
- **DoD / розблоковує:** regular Friend і Arena variant ділять один business
  command без generic service; розблоковує `F-03`.

#### F-03 — Delivered-push quota accounting

- **Мета / risk / залежності:** закрити quota portion `AR-014` без pre-send
  terminal marker; `R3`; `F-02`, Slice 3, preflight `PF-11`.
- **Файли та зміни:** змінити
  `app/bot/handlers/gameplay_flows/friend_challenge_push_quota.py::reserve_duel_push_slot`
  і `app/workers/tasks/friend_challenges_async.py`; decision transaction через
  `OutgoingEffectWriterPort.put_once` створює `friend.push.v1`, а delivered
  outcome має explicit authority.
- **Транзакція / БД / зовнішні ефекти:** competition use case owns quota
  decision + session-bound outgoing row; dispatcher sends after commit; provider
  failure не consume-ить terminal delivered quota.
- **Тести:** concurrent quota boundary, provider fail/retry/manual replay,
  source rollback, no pre-send terminal marker, one business decision/row.
- **Rollout / rollback / legacy:** відкрити другий staged slot
  `FRIEND_DELIVERY_MIGRATION_STAGE=LEGACY → QUOTA_NEW`; no dual-send; rollback
  drains pending; R3 observation.
- **DoD / розблоковує:** quota semantics відповідає approved `PF-11`, а failed
  effect видимий і recoverable; розблоковує `F-04`.

#### F-04 — Durable last-chance and deadline reminders

- **Мета / risk / залежності:** закрити deadline portion `AR-015` одним
  recoverable flow; `R2`; `F-03`.
- **Файли та зміни:** змінити
  `friend_challenges_deadline_decisions.py` і deadline task у
  `friend_challenges_async.py`; через public writer створювати versioned
  `friend.deadline_reminder.v1` зі stable challenge/deadline key.
- **Транзакція / БД / зовнішні ефекти:** short competition decision transaction
  inserts effect; scanner/dispatcher sends post-commit; deadline scan crash не
  змінює challenge state двічі.
- **Тести:** due/not-due/terminal challenge, scan crash/wakeup failure,
  provider retry, duplicate deadline tick, same-row replay.
- **Rollout / rollback / legacy:** delivery stage
  `QUOTA_NEW → QUOTA_DEADLINE_NEW`; one selected sender; ≥7 stable days for
  reminder portion, pending rows drain.
- **DoD / розблоковує:** failed reminder не suppress-ить майбутню repair;
  розблоковує `F-05`.

#### F-05 — Durable friend proof-card delivery

- **Мета / risk / залежності:** закрити friend part `AR-016` і cycle `AR-006`;
  `R2`; `F-04`.
- **Файли та зміни:** змінити
  `app/bot/handlers/gameplay_proof_cards.py`,
  `friend_answer_completion_flow.py` і
  `workers/tasks/friend_challenges_proof_cards.py`; completion через public
  writer записує `friend.proof_card.v1`, rendering/sending — adapter.
- **Транзакція / БД / зовнішні ефекти:** source effect atomic with completion;
  render/Telegram through dispatcher after commit; item has stable key.
- **Тести:** commit/enqueue gap repaired by scanner, render/provider failure,
  replay, no local import cycle, real entrypoint.
- **Rollout / rollback / legacy:** delivery stage
  `QUOTA_DEADLINE_NEW → ALL_NEW`; cohort/full, ≥7 stable days; pending rows
  always drain.
- **DoD / розблоковує:** proof delivery recoverable й bot не imports worker;
  розблоковує `F-06`.

#### F-06 — Friend staged-path cleanup

- **Мета / risk / залежності:** закрити обидва Friend write slots; `R3`;
  `F-02` і final delivery stage `F-05` full cutover, ≥14 stable days + full
  friend cycle measured from `F-05`.
- **Файли та зміни:** видалити duplicate branches із
  `friend_lobby_flow.py`, `friend_challenge_flow.py`,
  `friend_challenges_async.py` і `gameplay_proof_cards.py`; видалити raw
  push/deadline/proof senders, `FRIEND_ACCESS_MIGRATION_STAGE`,
  `FRIEND_DELIVERY_MIGRATION_STAGE`, obsolete tests і registry rows.
- **Транзакція / БД / зовнішні ефекти:** only competitions application/shared
  workflow, public writer and dispatcher; schema cleanup deferred.
- **Тести:** full create/accept/complete/deadline/proof regression, concurrent
  caps, architecture/registry/settings guards, zero fallback.
- **Rollout / rollback / legacy:** forward fix; durable pending retained;
  staged entry видаляється лише після longest observation.
- **DoD / розблоковує:** Friend займає zero slots і має one path per effect;
  розблоковує tournaments.

### Daily Cup and private tournaments

#### T-01 — Tournament lifecycle application UoW

- **Мета / risk / залежності:** прибрати pre-commit enqueue `AR-017`; `R3`;
  `F-06`.
- **Файли та зміни:** створити
  `app/modules/competitions/tournaments/application/advance_lifecycle.py` і
  UoW; змінити `game/tournaments/lifecycle.py`,
  `lifecycle_state.py`, `workers/tasks/tournaments_async.py` і
  Daily Cup round task; disabled new path уміє записати один explicit,
  versioned lifecycle delivery command через injected
  `OutgoingEffectWriterPort.put_once` і повертає DTO, але не enqueue-ить у
  broker та не викликає transport.
- **Транзакція / БД / зовнішні ефекти:** lifecycle use case owns locks,
  settlement, next-round rows і allowlisted
  `tournament.round_messaging_requested.v1` command у `outgoing_deliveries` in
  one transaction; session-bound writer не commit-ить; Telegram поза
  transaction, generic event bus не вводиться.
- **Тести:** round/deadline concurrency, pending match settlement, completion,
  commit failure, no precommit task visibility, private/Daily variants.
- **Rollout / rollback / legacy:** registry slot і new code deploy-яться, але
  `TOURNAMENT_LIFECYCLE_MIGRATION_STAGE=LEGACY`; лише pure
  standings/transition shadow. Production producer та lifecycle routing не
  активуються до `T-04`, де explicit handler ship-иться в тому самому release
  gate.
- **DoD / розблоковує:** lifecycle code не imports workers; no enqueue before
  commit; new producer disabled і unknown type неможливий; розблоковує
  registration delivery.

#### T-02 — Registration notification delivery

- **Мета / risk / залежності:** перенести один registration effect з batch
  sender; `R2`; `T-01`, Slice 3.
- **Файли та зміни:** змінити registration branch у
  `tournaments_messaging.py`; source use case через public writer створює one
  `tournament.registration.v1` row per recipient/content version.
- **Транзакція / БД / зовнішні ефекти:** registration transaction owns rows;
  dispatcher sends after commit; message-id CAS per item.
- **Тести:** duplicate registration, commit/wakeup failure, provider retry,
  edit/send version, item key/digest.
- **Rollout / rollback / legacy:** відкрити другий slot
  `TOURNAMENT_DELIVERY_MIGRATION_STAGE=LEGACY → REGISTRATION_NEW`; no dual-send,
  ≥7 stable days.
- **DoD / розблоковує:** registration batch failure не губить окремого
  recipient; розблоковує `T-03`.

#### T-03 — Cancellation notification delivery

- **Мета / risk / залежності:** перенести один cancellation effect; `R2`;
  `T-02`.
- **Файли та зміни:** змінити cancellation branch у
  `app/workers/tasks/tournaments_messaging.py`; створювати versioned
  `tournament.cancellation.v1` item per affected recipient.
- **Транзакція / БД / зовнішні ефекти:** cancellation mutation + outgoing rows
  atomic through session-bound writer; Telegram post-commit.
- **Тести:** cancel replay, partial recipient/provider failure, cancel-vs-start
  race, same-row replay і source rollback.
- **Rollout / rollback / legacy:** delivery stage
  `REGISTRATION_NEW → REGISTRATION_CANCELLATION_NEW`; one sender per effect,
  pending drain.
- **DoD / розблоковує:** cancellation delivery має item-level recovery;
  розблоковує `T-04`.

#### T-04 — Round-start and turn-reminder delivery

- **Мета / risk / залежності:** materialize lifecycle round command без
  whole-batch marker; `R2`; `T-03`.
- **Файли та зміни:** створити explicit handler
  `HandleTournamentRoundMessagingRequestedV1`; змінити
  `daily_cup_messaging.py` і `daily_cup_messaging_delivery.py` так, щоб
  `tournament.round_messaging_requested.v1` створював child row per recipient;
  додати handler до compile-time
  `app/bootstrap/outgoing_effect_handlers.py`.
- **Транзакція / БД / зовнішні ефекти:** internal handler поза messaging claim
  transaction idempotently materializes children зі stable parent/child keys;
  each send/mark independent.
- **Тести:** crash after child N, parent replay, earlier child already sent,
  missing recipient, turn versioning, partial provider failure.
- **Rollout / rollback / legacy:** handler deploy/register перевіряється до
  flags; одним release gate lifecycle stage переходить `LEGACY → NEW`, а
  delivery stage — `REGISTRATION_CANCELLATION_NEW → ROUND_NEW`; rollback keeps
  parent/children repairable; one full round observation.
- **DoD / розблоковує:** round batch crash leaves every item recoverable;
  розблоковує `T-05`.

#### T-05 — Final result and standings delivery

- **Мета / risk / залежності:** закрити critical final-result portion
  `AR-021`; `R3`; `T-04`.
- **Файли та зміни:** змінити final-result branches у
  `tournaments_messaging.py` і `daily_cup_messaging.py`; source result command
  через writer створює `tournament.final_result.v1` item per recipient/version.
- **Транзакція / БД / зовнішні ефекти:** terminal competition mutation +
  outgoing items atomic; each critical notification dispatched independently.
- **Тести:** terminal transition race, crash after item N, provider-ack window,
  replay, standings digest/version mismatch, critical-age alert.
- **Rollout / rollback / legacy:** delivery stage `ROUND_NEW → RESULT_NEW`;
  pure recipient/payload digest shadow, internal/private then Daily, R3
  observation.
- **DoD / розблоковує:** committed final result не приховується whole-batch
  failure; розблоковує `T-06`.

#### T-06 — Private-tournament proof-card delivery

- **Мета / risk / залежності:** закрити private proof portion `AR-016`; `R2`;
  `T-05`.
- **Файли та зміни:** adapt
  `app/workers/tasks/tournaments_proof_cards.py` і
  `app/workers/tasks/tournaments_proof_cards_delivery.py`; one
  `tournament.private_proof_card.v1` row per participant, no lock during
  render/send.
- **Транзакція / БД / зовнішні ефекти:** short source/item transactions;
  render/Telegram after claim; provider file id stored via CAS outcome.
- **Тести:** lock-skip retry, render/provider crash, cached file id, explicit
  resend same business identity, item-level idempotency.
- **Rollout / rollback / legacy:** delivery stage
  `RESULT_NEW → PRIVATE_PROOF_NEW`; private cohort/full, ≥7 days; pending drain.
- **DoD / розблоковує:** private proof no longer holds SQL lock and is
  recoverable; розблоковує `T-07`.

#### T-07 — Tournament delivery-stage cleanup

- **Мета / risk / залежності:** звільнити delivery slot до reward migration;
  `R3`; final stage `T-06` full cutover ≥14 stable days + complete
  private/Daily cycle, бо весь staged slot успадковує highest risk tier.
- **Файли та зміни:** видалити migrated legacy branches із
  `tournaments_messaging.py`, `daily_cup_messaging.py`,
  `daily_cup_messaging_delivery.py`, `tournaments_proof_cards.py` і
  `tournaments_proof_cards_delivery.py`; видалити
  `TOURNAMENT_DELIVERY_MIGRATION_STAGE`, obsolete tests і registry entry; Daily
  proof/reward trigger ще не чіпати.
- **Транзакція / БД / зовнішні ефекти:** lifecycle slot лишається active;
  dispatcher is sole sender for migrated effects, pending retained.
- **Тести:** zero legacy delivery call/metric, full private/Daily messaging,
  registry/settings guards, pending parent/child drain.
- **Rollout / rollback / legacy:** forward fix after longest observation;
  historical rows/schema retained.
- **DoD / розблоковує:** tournament delivery slot closed, lifecycle slot єдиний
  active; розблоковує `T-08`.

#### T-08 — Daily Cup final-standings reward event

- **Мета / risk / залежності:** відв’язати reward correctness від proof-card
  worker; `R3`; `T-07`, preflight `PF-07`.
- **Файли та зміни:** terminal lifecycle через writer створює internal
  `daily_cup.final_standings.v1`; створити economy handler
  `HandleDailyCupFinalStandingsV1` і зареєструвати його в
  `app/bootstrap/outgoing_effect_handlers.py` до producer flag; payload містить
  tournament id, completed-at, participant count, standings digest, ≤3 eligible
  user/rank pairs і pinned reward-policy version. Keys:
  `daily-cup:{tournament_id}:final-standings:v1`,
  `daily-cup:{tournament_id}:rank:{rank}:user:{user_id}:grant:v1` і відповідний
  `...:notification:v1`.
- **Транзакція / БД / зовнішні ефекти:** competition source commit persists
  parent; explicit handler owns one economy grant/ledger/entitlement UoW і в
  ньому створює Telegram reward rows через same writer; parent `SENT` CAS лише
  після receiver commit. No broad competition+economy workflow.
- **Тести:** source/wakeup failure, handler pre-commit failure, economy commit/
  parent-CAS failure, replay already-granted reward, same key/different digest,
  notification failure does not repeat grant, zero reward mismatch.
- **Rollout / rollback / legacy:** explicit handler map deploy/test first, потім
  відкрити slot
  `TOURNAMENT_FINALIZATION_MIGRATION_STAGE=LEGACY → REWARD_NEW`; dry/pure shadow,
  internal/full, ≥14 days + Daily Cup cycle; pending events retryable.
- **DoD / розблоковує:** reward grant idempotent і не залежить від proof send;
  розблоковує safe Daily proof migration `T-09`.

#### T-09 — Daily Cup proof-card delivery

- **Мета / risk / залежності:** закрити Daily proof portion `AR-016` після
  extraction reward trigger; `R2`; `T-08`.
- **Файли та зміни:** adapt
  `daily_cup_proof_cards.py`, `daily_cup_proof_cards_delivery.py` і runtime;
  видалити виклик `_grant_winner_rewards_once` з proof orchestration; one
  `daily_cup.proof_card.v1` row per participant.
- **Транзакція / БД / зовнішні ефекти:** proof source/item transactions short;
  render/Telegram after claim; reward handler незалежний і вже active.
- **Тести:** regression, що proof crash/skip не suppress-ить reward; render/
  provider crash, cached file id, item replay, manual single-user resend.
- **Rollout / rollback / legacy:** finalization stage
  `REWARD_NEW → ALL_NEW`; Daily cohort/full, ≥7 stable days; reward route не
  повертається на proof worker.
- **DoD / розблоковує:** Daily proof recoverable без reward side effect;
  розблоковує `T-10`.

#### T-10 — Tournament lifecycle/finalization cleanup

- **Мета / risk / залежності:** close remaining tournament slots; `R3`; `T-01`
  lifecycle і finalization final stage `T-09` full cutover ≥14 stable days +
  complete private/Daily cycle measured from `T-09`.
- **Файли та зміни:** видалити legacy helpers із
  `game/tournaments/lifecycle.py`, `workers/tasks/tournaments_async.py`,
  `daily_cup_proof_cards.py` і `daily_cup_proof_cards_runtime.py`; видалити
  `TOURNAMENT_LIFECYCLE_MIGRATION_STAGE`,
  `TOURNAMENT_FINALIZATION_MIGRATION_STAGE`, obsolete tests і registry entries;
  historical columns лишити до schema cleanup.
- **Транзакція / БД / зовнішні ефекти:** only new lifecycle UoW, explicit
  internal handlers, public writer and dispatcher.
- **Тести:** `make test-tournaments`, full Daily/private lifecycle,
  item-delivery/reward failure windows, architecture/registry/settings.
- **Rollout / rollback / legacy:** forward fix; all pending parent/child/
  Telegram rows preserved and drained.
- **DoD / розблоковує:** tournament має one path per command/effect і zero
  active slots; розблоковує Payments.

### Payments reliability

#### P-01 — Purchase saleability application invariant

- **Мета / risk / залежності:** закрити `AR-025` без architecture move; `R3`;
  `T-10`.
- **Файли та зміни:** змінити
  `app/economy/purchases/catalog.py::is_product_available_for_sale`,
  `purchases/service/init.py::init_purchase` і errors; disabled/noncanonical
  sale відхиляти до DB mutation, internal reward grants не змінювати.
- **Транзакція / БД / зовнішні ефекти:** existing purchase transaction owner;
  rejected path має zero DB/external effects.
- **Тести:** direct service cannot create disabled/alias purchase; valid catalog
  unchanged; bot and service policy agree.
- **Rollout / rollback / legacy:** direct policy fix після characterization;
  no flag і no unsafe legacy fallback; product availability change не входить
  в цей correctness PR.
- **DoD / розблоковує:** saleability не залежить від bot UI; розблоковує payment
  policy milestone `P-02`.

#### P-02 — Paid-history promo eligibility

- **Мета / risk / залежності:** закрити `AR-026`; `R3`; `P-01`, preflight
  `PF-08`.
- **Файли та зміни:** змінити
  `promo/redeem_validation.py::ensure_purchase_eligibility` на
  `PurchasesRepo.count_paid_purchases_for_user`; окремо зберегти визначення
  `new_users_only` та `first_purchase_only`.
- **Транзакція / БД / зовнішні ефекти:** promo application transaction owns
  eligibility/reservation; no external effect.
- **Тести:** CREATED/FAILED/zero-cost reward не блокують; paid
  `PAID_UNCREDITED/CREDITED/REFUNDED` semantics згідно preflight; pure decision
  shadow, zero mismatch except approved policy change.
- **Rollout / rollback / legacy:** відкрити
  `PAYMENT_POLICY_MIGRATION_STAGE=LEGACY → PAID_HISTORY_NEW`; pure decision
  shadow then cohort/full; no dual mutation, rollback old decision only during
  observation.
- **DoD / розблоковує:** eligibility відповідає documented paid history;
  розблоковує observation cleanup `P-03`.

#### P-03 — Paid-history policy legacy cleanup

- **Мета / risk / залежності:** закрити policy slot до payment state migration;
  `R3`; `P-02` full cutover ≥14 stable days + one billing/promo cycle.
- **Файли та зміни:** видалити legacy eligibility branch, policy staged setting,
  obsolete comparison tests і registry entry; documented
  `new_users_only/first_purchase_only` contract лишається.
- **Транзакція / БД / зовнішні ефекти:** one eligibility decision; no schema or
  external effect.
- **Тести:** zero legacy caller/flag, paid-status matrix, promo regression,
  registry/settings guard.
- **Rollout / rollback / legacy:** forward fix after zero mismatch or approved
  policy delta; old decision не resurrect-ити неявно.
- **DoD / розблоковує:** policy slot closed; розблоковує `P-04`.

#### P-04 — Authoritative payment evidence lifecycle

- **Мета / risk / залежності:** закрити payment half `AR-024`; `R3`; `P-03`,
  transport-compatible with later `C-01`.
- **Файли та зміни:** у
  `app/db/models/payment_inbox.py::{TelegramUpdateInbox,PaymentEvent}` і
  `app/db/repo/payment_inbox_repo.py::PaymentEventsRepo` зробити `PaymentEvent`
  єдиною authority business outcome; `TelegramUpdateInbox` лишити immutable
  intake/provenance. Додати `PROCESSING` до
  `RECEIVED → PROCESSING → APPLIED/RETRY/FAILED/REVIEW`, `state_version`,
  `processing_token`, `attempt_count`, `next_retry_at`, timestamps і bounded
  reason в Alembic revision. Змінити
  `app/services/payment_update_evidence.py::store_payment_update_evidence`,
  `app/bot/handlers/payments.py::{handle_precheckout,handle_successful_payment,handle_refunded_payment}`
  та відповідні functions у `payments_runtime.py`: aiogram `Update.update_id`
  резолвиться в `payment_event_id`, і обидва IDs входять у command DTO.
  Додати
  `app/workers/tasks/payment_event_repair.py::{repair_payment_events_async,repair_payment_events}`
  і
  `::{replay_payment_event_async,replay_payment_event,PAYMENT_EVENT_REPAIR_HANDLERS}`,
  та explicit schedule у `payments_reliability_schedule.py`. До першого
  `RETRY` producer merge static handlers для retryable
  `SUCCESSFUL_PAYMENT/REFUNDED_PAYMENT` вже існують; `PRE_CHECKOUT` не є
  retryable.
- **Транзакція / БД / зовнішні ефекти:** `ProcessedUpdate` лишається тільки
  transport lease/status і не визначає payment success. Payment application UoW
  locks purchase + `PaymentEvent`, CAS-ить token/version і атомарно commit-ить
  purchase mutation та business outcome; late `FAILED/RETRY` не може overwrite
  `APPLIED`. Provider/broker виконується поза SQL. `RETRY` дозволений лише з
  `attempt_count/next_retry_at` і bounded replay input: scanner claim-ить row,
  commit-ить lease, після commit enqueue-ить stable `payment_event_id`; missed
  enqueue підбирає наступний scan. Expired pre-checkout не replay-иться, а йде
  в `REVIEW`.
- **Тести:** entrypoint correlation `update_id → inbox → payment_event_id →
  purchase`; duplicate webhook/evidence, two-session outcome race, late
  failure/retry versus `APPLIED`, crash before/after joint commit, retry claim,
  missed enqueue і repair replay; real aiogram path, real PostgreSQL migration
  and CAS tests.
- **Rollout / rollback / legacy:** відкрити staged slot
  `PAYMENT_APPLICATION_MIGRATION_STAGE=LEGACY → EVIDENCE_NEW`; additive columns,
  consumer/repair + schedule deploy before RETRY producer, then reader and
  cohort; no destructive status rewrite. Existing
  `TelegramUpdateInbox.status` не використовується як outcome і видаляється лише
  після separate inventory/cleanup.
- **DoD / розблоковує:** кожна payment command має exact correlated
  `PaymentEvent`; terminal outcome монотонний, retry має active repair, і
  evidence не лишається вічно `RECEIVED/PROCESSING`; розблоковує `P-05`.

#### P-05 — Pre-checkout validation command

- **Мета / risk / залежності:** винести одну pre-checkout policy boundary;
  `R3`; `P-04`.
- **Файли та зміни:** створити
  `app/modules/economy/payments/application/validate_precheckout.py` і public
  DTO/error contract; зробити відповідну branch
  `bot/handlers/payments_runtime.py` thin.
- **Транзакція / БД / зовнішні ефекти:** application use case owns short
  purchase read/lock transaction; Telegram callback answer after commit.
- **Тести:** amount/currency/payload/user/status mismatch, replay, disabled
  product, callback failure and one real aiogram entrypoint.
- **Rollout / rollback / legacy:** application stage
  `EVIDENCE_NEW → PRECHECKOUT_NEW`; pure decision shadow, internal test purchase
  then cohort; zero invariant mismatch.
- **DoD / розблоковує:** handler не володіє validation/SQL policy;
  розблоковує `P-06`.

#### P-06 — Mark-paid and `PAID_UNCREDITED` checkpoint command

- **Мета / risk / залежності:** зберегти durable paid checkpoint окремим
  application behavior; `R3`; `P-05`.
- **Файли та зміни:** створити
  `app/modules/economy/payments/application/mark_purchase_paid.py`; adapt paid
  update branch in `payments_runtime.py` і evidence outcome mapping.
- **Транзакція / БД / зовнішні ефекти:** one economy UoW locks purchase and
  idempotently writes provider evidence + `PAID_UNCREDITED`; entitlement/ledger
  ще не credit-яться в цьому command.
- **Тести:** duplicate provider update, CREATED/FAILED/already credited,
  mismatched payload, crash immediately after paid commit, PostgreSQL races.
- **Rollout / rollback / legacy:** stage
  `PRECHECKOUT_NEW → MARK_PAID_NEW`; internal/cohort, old recovery remains
  available, no dual state mutation.
- **DoD / розблоковує:** paid money завжди має recoverable checkpoint;
  розблоковує `P-07`.

#### P-07 — Idempotent entitlement and ledger credit command

- **Мета / risk / залежності:** атомарно credit-нути один paid purchase; `R3`;
  `P-06`, `R1-02`.
- **Файли та зміни:** створити
  `app/modules/economy/payments/application/credit_paid_purchase.py` і SQL UoW;
  adapt current credit branch/repositories without changing ledger keys.
- **Транзакція / БД / зовнішні ефекти:** UoW owns
  `PAID_UNCREDITED → CREDITED`, entitlement/asset and ledger in one transaction;
  no provider/Telegram I/O.
- **Тести:** concurrent credit, every status replay, ledger+entitlement
  atomicity, failure at each flush, stable idempotency key, real PostgreSQL.
- **Rollout / rollback / legacy:** stage
  `MARK_PAID_NEW → CREDIT_NEW`; pure result shadow/internal purchases/cohort;
  zero money/reward mismatch.
- **DoD / розблоковує:** credit mutation є single command і не дублюється;
  розблоковує `P-08`.

#### P-08 — `PAID_UNCREDITED` recovery command and thin worker

- **Мета / risk / залежності:** відновлювати checkpoint через той самий credit
  command; `R3`; `P-07`.
- **Файли та зміни:** створити
  `app/modules/economy/payments/application/recover_paid_purchase.py::{RecoverPaidPurchase,RecoverPaidPurchaseCommand}`;
  зробити
  `workers/tasks/payments_reliability_async.py::_recover_single_purchase` thin;
  explicit `RecoverPaidPurchaseResult`; у
  `payment_event_repair.py::PAYMENT_EVENT_REPAIR_HANDLERS` статично зареєструвати
  `SUCCESSFUL_PAYMENT → RecoverPaidPurchase` до ввімкнення producer stage.
- **Транзакція / БД / зовнішні ефекти:** worker викликає application UoW;
  command locks correlated `PaymentEvent` + purchase і в одному commit
  переводить `PAID_UNCREDITED → CREDITED` та event `RETRY/PROCESSING → APPLIED`;
  provider evidence input load поза mutation transaction; ops alert post-commit.
- **Тести:** crash-after-paid recovery, concurrent worker/update, max attempts,
  retry/review mapping, alert failure, real worker entrypoint.
- **Rollout / rollback / legacy:** stage `CREDIT_NEW → ALL_NEW`; internal backlog
  dry run, cohort/full; old recovery route retained only for R3 observation.
- **DoD / розблоковує:** handler/worker не owns SQL policy і durable checkpoint
  fully recoverable; розблоковує `P-09`.

#### P-09 — Telegram Stars provider-fetch adapter

- **Мета / risk / залежності:** ізолювати provider pagination/I/O з hotspot;
  `R3`; `P-08`, preflight `PF-05`.
- **Файли та зміни:** створити
  `app/modules/economy/payments/adapters/telegram_stars/provider_history.py`;
  extract fetch/pagination from
  `run_telegram_stars_reconciliation_async` behind bounded application port.
- **Транзакція / БД / зовнішні ефекти:** Telegram history fetch has no open SQL
  transaction; adapter returns immutable bounded pages/DTOs, no mutation.
- **Тести:** pagination, cursor loop/limit, timeout/rate limit/provider error,
  payload validation and adapter contract.
- **Rollout / rollback / legacy:** disabled composition only; no routing flag or
  write slot; old reconciler still active.
- **DoD / розблоковує:** provider I/O owner isolated and bounded;
  розблоковує `P-10`.

#### P-10 — Pure reconciliation classification and revalidation plan

- **Мета / risk / залежності:** isolate exact/ambiguous/refund policy decision;
  `R3`; `P-09`, `PF-08`.
- **Файли та зміни:** створити
  `app/modules/economy/payments/application/classify_reconciliation.py::{classify_reconciliation,ReconciliationPlan,ReconciliationDecision}`;
  extract pure rules from `services/payment_reconciliation.py` і current worker;
  immutable plan names required purchase/evidence revalidation before apply.
- **Транзакція / БД / зовнішні ефекти:** pure decision has none; eventual
  mutation must re-read/lock rather than trust provider snapshot.
- **Тести:** exact/no/ambiguous match, batch refund, currency/amount mismatch,
  stale local state, bounded payload and golden characterization; zero mismatch.
- **Rollout / rollback / legacy:** shadow only, no writer/slot; policy delta
  blocks until `PF-08` approval.
- **DoD / розблоковує:** reconciliation decision reproducible without I/O;
  розблоковує `P-11`.

#### P-11 — Reconciliation review persistence and output port

- **Мета / risk / залежності:** persist ambiguous outcomes independently from
  alerts; `R3`; `P-10`.
- **Файли та зміни:** adapt `PaymentReconciliationReview` model/repo, next
  Alembic revision and application output port; store bounded evidence digest,
  reason, state and correlation, not provider secret/raw payload.
- **Транзакція / БД / зовнішні ефекти:** short application-owned review
  transaction; ops notification after commit through separate port.
- **Тести:** idempotent review upsert, same-key conflict, retry/resolution state,
  migration/privacy/admin query, alert failure does not lose review.
- **Rollout / rollback / legacy:** additive reader-first deploy, disabled writer;
  no write slot until `P-12`.
- **DoD / розблоковує:** ambiguous payment has durable operator-visible state;
  розблоковує `P-12`.

#### P-12 — Exact-match reconciliation auto-recovery handler

- **Мета / risk / залежності:** apply only proven exact plans through new
  commands; `R3`; `P-08`, `P-11`, preflights `PF-07/PF-08`.
- **Файли та зміни:** створити
  `app/modules/economy/payments/application/reconcile_exact_payment.py::{ReconcileExactPayment,ReconcileExactPaymentCommand}`;
  додати transaction-participant symbols
  `mark_purchase_paid.py::mark_paid_in_uow` і
  `credit_paid_purchase.py::credit_in_uow`; зробити
  `app/workers/tasks/payments_reliability_async.py::run_telegram_stars_reconciliation_async`
  thin adapter.
- **Транзакція / БД / зовнішні ефекти:** provider pages fetched first; each
  exact match входить в один outer `ReconcileExactPayment` economy UoW,
  revalidates/locks purchase + evidence і викликає лише `*_in_uow`
  participants; public commands, що відкривають transaction, не nest-яться.
  Review persistence і alert виконуються відповідно в тому самому UoW та
  post-commit.
- **Тести:** dry run, exact concurrent recovery, revalidation conflict,
  pagination/backlog, provider failure, batch refund routed review, PostgreSQL
  race and zero-mismatch shadow.
- **Rollout / rollback / legacy:** open second slot
  `PAYMENT_RECONCILIATION_MIGRATION_STAGE=LEGACY → EXACT_NEW`; existing
  `telegram_stars_reconciliation_dry_run` is a kill switch, not a legacy/new
  slot; auto recovery off until evidence approved.
- **DoD / розблоковує:** no auto recovery without exact revalidation and durable
  review fallback; розблоковує `P-13`.

#### P-13 — Payment application-stage legacy cleanup

- **Мета / risk / залежності:** звільнити application slot before refund work;
  `R3`; `P-08` ≥14 stable days + billing cycle, `P-12` uses new commands.
- **Файли та зміни:** видалити legacy evidence outcome mapping,
  precheckout/mark-paid/credit/recovery branches, application staged setting,
  obsolete mocks/tests і registry entry; keep `PAID_UNCREDITED` and
  authoritative live evidence.
- **Транзакція / БД / зовнішні ефекти:** only new economy payment UoWs; recon
  slot stays active.
- **Тести:** end-to-end pay/credit/recover, all checkpoint crash windows, zero
  legacy usage/import, registry/settings guards.
- **Rollout / rollback / legacy:** forward fix after observation; evidence/schema
  retained.
- **DoD / розблоковує:** application slot closed, reconciliation is sole active
  payment slot; розблоковує `P-14`.

#### P-14 — Refund and available-benefit clawback command

- **Мета / risk / залежності:** isolate чинний refund invariant і не приписувати
  `AR-027` непідтверджену product semantics; `R3`; `P-13`.
- **Файли та зміни:** створити
  `app/modules/economy/payments/application/refund_purchase.py::{RefundPurchase,RefundPurchaseCommand,RefundOutcome}`
  з полями `financial_reversal_amount`, `recovered_asset_amount`,
  `unrecovered_asset_amount`; adapt
  `app/economy/purchases/service/refund.py` і
  `app/bot/handlers/payments_runtime.py::refund_payment_update`. У цьому PR не
  додавати debt/unrecovered business state, model чи schema.
- **Транзакція / БД / зовнішні ефекти:** economy UoW atomically handles
  purchase/refund, full financial ledger reversal і clawback лише доступного
  gameplay asset; різниця повертається як `unrecovered_asset_amount`, але не
  створює debt. Correlated `PaymentEvent` стає `APPLIED` у тому самому commit;
  provider confirmation input prevalidated; no network.
- **Тести:** idempotent full/partial available clawback, consumed benefit не
  створює negative balance/debt, full ledger reversal, exact `RefundOutcome`,
  concurrent refund/credit, evidence CAS і provider mismatch; PostgreSQL.
- **Rollout / rollback / legacy:** open freed slot
  `PAYMENT_REFUND_MIGRATION_STAGE=LEGACY → REFUND_NEW`; preserve current
  financial semantics; pure characterization shadow/cohort, zero mismatch.
  Будь-яка майбутня debt/collection policy потребує окремої amendment,
  milestone, model/repo/migration і product/finance approval; вона не входить у
  цей план.
- **DoD / розблоковує:** financial reversal і recovered/unrecovered gameplay
  asset виміряні окремо без нового debt state; розблоковує `P-15`.

#### P-15 — Manual-review resolve, replay and suppress commands

- **Мета / risk / залежності:** make operator decisions explicit and auditable;
  `R3`; `P-12`, `P-14`.
- **Файли та зміни:** створити
  `app/modules/economy/payments/application/review_actions.py::{ResolvePaymentReview,ReplayPaymentReview,SuppressPaymentReview}`
  і command DTOs з `review_id`, expected version та bounded reason; створити
  `app/api/routes/admin/payment_reviews.py::{resolve_payment_review,replay_payment_review,suppress_payment_review}`
  та зареєструвати router. Кожний money-affecting action вимагає
  `AdminPrincipal.role == "super_admin"` і verified current 2FA.
- **Транзакція / БД / зовнішні ефекти:** resolve/replay CAS-lock-ить review,
  payment event і purchase та викликає `*_in_uow` participant, тому payment
  mutation + review `RESOLVED` commit-яться в одному UoW; suppress CAS-ить
  `OPEN → SUPPRESSED` без money mutation. Alert/wakeup лише after commit; no
  cloned payment effect.
- **Тести:** звичайний admin і missing/expired 2FA denied; concurrent operator
  action, stale version, bounded reason/audit, idempotent replay, suppress
  bounds, payment mutation once; crash before commit leaves both unchanged,
  crash after commit leaves both resolved; real FastAPI + PostgreSQL.
- **Rollout / rollback / legacy:** uses existing reconciliation/refund slots; no
  third slot/flag; commands enabled after admin acceptance.
- **DoD / розблоковує:** review recovery safe without ad-hoc SQL;
  розблоковує `P-16`.

#### P-16 — Payment audit and post-commit alert adapters

- **Мета / risk / залежності:** remove audit/alert I/O from payment transactions;
  `R3`; `P-14`, `P-15`.
- **Файли та зміни:** створити
  `app/modules/economy/payments/application/ports.py::{PaymentAuditPort,PaymentAlertPort}`,
  `app/modules/economy/payments/adapters/audit_ledger.py::AuditLedgerPaymentAdapter`
  і
  `app/modules/economy/payments/adapters/ops_alerts.py::OpsPaymentAlertAdapter`;
  extract `send_ops_alert` calls from refund/reconciliation runtime; bounded
  event types/correlation and retry policy.
- **Транзакція / БД / зовнішні ефекти:** business/review UoW persists audit
  command where critical; network alert only post-commit and cannot roll back
  money state.
- **Тести:** commit/alert ordering, alert failure/retry, no secret/PII payload,
  refund/review result unchanged, operator correlation.
- **Rollout / rollback / legacy:** direct adapter switch inside two existing
  staged routes; no new slot; rollback preserves persisted audit/review state.
- **DoD / розблоковує:** alert failure cannot corrupt payment outcome;
  розблоковує `P-17`.

#### P-17 — Payment final cutover and hotspot cleanup

- **Мета / risk / залежності:** завершити Payments vertical slice; `R3`;
  `P-12/P-14` full cutover ≥14 stable days + complete
  billing/refund/reconciliation cycle, `P-15/P-16`.
- **Файли та зміни:** remove remaining reconciliation/refund legacy branches in
  `payments_reliability_async.py`, staged settings, obsolete mocks/tests і both
  registry entries; не видаляти `PAID_UNCREDITED`, live evidence/reviews.
- **Транзакція / БД / зовнішні ефекти:** only economy application UoWs,
  explicit provider/review/audit adapters; alerts/delivery post-commit.
- **Тести:** end-to-end pay/credit/recover/refund/reconcile/review, all crash
  windows, zero invariant mismatch, architecture/registry/settings guards.
- **Rollout / rollback / legacy:** full-cutover evidence reviewed separately;
  forward fix only, additive schema retained.
- **DoD / розблоковує:** hotspot decomposed by behaviors, not line count; zero
  payment slots and all invariants preserved; розблоковує Further cleanup.

### Further cleanup

#### C-01 — Incoming update lease schema and claim protocol

- **Мета / risk / залежності:** дати `AR-022` і generic half `AR-024` durable
  protocol без runtime switch; `R3`; `P-17`, payload/retention preflight
  `PF-06`.
- **Файли та зміни:** розширити
  `app/db/models/processed_updates.py::ProcessedUpdate`,
  `app/db/repo/processed_updates_repo_slots.py::ProcessedUpdatesRepoSlotsMixin`
  і metrics repo; додати Alembic revision зі states
  `RECEIVED/PROCESSING/PROCESSED/RETRY/FAILED`, `attempt_count`,
  `processing_token`, `claimed_at`, `lease_until`, `heartbeat_at`,
  `next_retry_at`, bounded error fields та approved encrypted replay envelope
  (`payload_ciphertext`, hash/schema/key version, `replay_expires_at`).
- **Транзакція / БД / зовнішні ефекти:** repo exposes only short
  create/claim/heartbeat/outcome CAS operations. Token + nonexpired lease є
  authority; handler, broker і crypto I/O не виконуються всередині transaction.
  `PaymentEvent` не дублюється: це business outcome, `ProcessedUpdate` —
  transport.
- **Тести:** migration upgrade/clean DB, two independent PostgreSQL sessions
  claim one row, stale-token terminal CAS rejected, heartbeat extends matching
  lease only, retry ordering/indexes, envelope expiry/privacy.
- **Rollout / rollback / legacy:** additive schema deployed disabled; жодний
  webhook/worker producer ще не пише new lifecycle. No destructive downgrade;
  old columns/readers remain.
- **DoD / розблоковує:** schema/protocol review доводить one-owner claim і
  replayability without raw payload logging; розблоковує `C-02`.

#### C-02 — Incoming update runtime repair and cohort cutover

- **Мета / risk / залежності:** увімкнути repairable incoming lifecycle окремо
  від його schema й cleanup; `R3`; `C-01`, `P-17`, `PF-05/PF-06`.
- **Файли та зміни:** змінити
  `app/api/routes/telegram_webhook.py::telegram_webhook`,
  `app/workers/tasks/telegram_updates_processing.py::{process_update_async,_feed_update_with_trace}`,
  `app/workers/tasks/telegram_updates.py::process_telegram_update` і
  `telegram_updates_reliability.py`; лишити одну
  `_acquire_processing_slot`. Додати
  `INCOMING_UPDATE_MIGRATION_STAGE=LEGACY|PAYMENT_COHORT|COHORT|ALL_NEW` у
  `app/core/config_migrations.py`; додати
  `repair_stale_incoming_updates_async` + Celery task/schedule.
- **Транзакція / БД / зовнішні ефекти:** webhook encrypt-ить bounded payload,
  commit-ить `RECEIVED`, потім enqueue-ить; worker коротко claim-ить
  `PROCESSING`, heartbeat-ить і CAS-ить outcome, а aiogram handler працює без
  open SQL claim transaction. Scanner claim-ить expired/`RETRY`, commit-ить,
  decrypt-ить і enqueue-ить stable `update_id` after commit; missed enqueue
  лишається eligible. Payment outcome mapping посилається на `PaymentEvent`, не
  копіюється у transport state.
- **Тести:** real webhook → broker → worker path; worker loss before/after
  claim, missed initial/repair enqueue, long handler heartbeat, stale reclaim,
  old-token completion, duplicate delivery and payment correlation; two
  independent PostgreSQL sessions + barrier.
- **Rollout / rollback / legacy:** registry slot і monotonic
  `PAYMENT_COHORT → COHORT → ALL_NEW`; one route per update, no dual handler.
  Rollback stops routing new updates to new claims, але scanner/consumer
  продовжує drain already-created `RECEIVED/PROCESSING/RETRY` rows.
- **DoD / розблоковує:** stale/missed work має active repair, age alone не
  спричиняє double processing, full cutover evidence записане; розблоковує
  observation cleanup `C-03`.

#### C-03 — Incoming update legacy-slot cleanup

- **Мета / risk / залежності:** закрити incoming transport slot; `R3`; `C-02`
  full cutover ≥14 stable days + one complete update/payment retry cycle.
- **Файли та зміни:** видалити legacy acquire/status branches, duplicate
  `_acquire_processing_slot`, staged setting, obsolete retry mocks/tests і
  registry entry; retain new repo, scanner, crypto adapter та live nonterminal
  rows.
- **Транзакція / БД / зовнішні ефекти:** only lease/token CAS path remains;
  pending work drains, terminal encrypted payload follows approved retention.
- **Тести:** zero legacy branch/setting/import, pending-row drain across deploy,
  retention expiry, worker-loss regression і registry validator.
- **Rollout / rollback / legacy:** forward cleanup after clock; no DB downgrade
  і no deletion of nonterminal rows. Incident response pauses new webhook
  acceptance or ships forward fix while repair consumer stays live.
- **DoD / розблоковує:** incoming slot closed with zero legacy usage and no
  abandoned row; розблоковує final join `C-09`.

#### C-04 — Conflict-safe first-row energy and streak state

- **Мета / risk / залежності:** close tentative `AR-040`; `R3`; `P-17`.
- **Файли та зміни:** змінити
  `app/economy/energy/energy_models.py::get_or_create_state_for_update`,
  `app/db/repo/energy_repo.py::EnergyRepo.create_default_state`,
  `app/economy/streak/service.py::StreakService._get_or_create_state_for_update`
  і `app/db/repo/streak_repo.py::StreakRepo.create_default_state` на PostgreSQL
  upsert/savepoint + load-for-update.
- **Транзакція / БД / зовнішні ефекти:** current caller-owned UoW лишається
  owner у gameplay **і** refund call sites; repositories не commit-ять.
  `energy_state.user_id` і `streak_state.user_id` primary keys є conflict
  targets; no network/schema change.
- **Тести:** для energy і streak дві незалежні SQLAlchemy sessions синхронізує
  barrier перед missing-row insert; рівно один default row, loser recovery у
  usable transaction, no overwrite; окремо gameplay, refund, onboarding і
  legacy-user paths на real PostgreSQL.
- **Rollout / rollback / legacy:** direct forward-only conflict fix після
  PostgreSQL proof; no flag. Incident response pauses affected path і ships
  forward fix, але не повертає unsafe read-then-insert gap.
- **DoD / розблоковує:** first-row concurrency cannot abort either caller flow.
  Якщо live-інцидент не відтворюється, статичний race-gap усе одно усунено або
  milestone explicitly deferred окремим risk-рішенням; розблоковує `C-09`.

#### C-05 — Explicit composition roots and resource lifecycle

- **Мета / risk / залежності:** address proven structure of `AR-032` without
  claiming an unproven leak; `R2`; `P-17`, migrated adapters stable.
- **Файли та зміни:** create narrow API composition root in
  `app/bootstrap/api.py`; add FastAPI lifespan disposal around `app/main.py`,
  DB engine, Redis clients and API-owned dispatcher resources; bot/Celery
  composition already introduced slice-by-slice, no repository-wide move.
- **Транзакція / БД / зовнішні ефекти:** no business transaction change;
  startup/shutdown opens/closes runtime clients once per process.
- **Тести:** repeated API lifespan, client close/dispose, startup failure
  cleanup і no secret-dependent imports in test composition.
- **Rollout / rollback / legacy:** one API runtime surface in this PR; canary;
  rollback to prior lifespan without resurrecting local business state.
- **DoD / розблоковує:** ownership/lifetime explicit for migrated clients;
  no broad service locator; розблоковує worker-specific `C-06`.

#### C-06 — Worker limits, heartbeat and container health

- **Мета / risk / залежності:** close `AR-029`; `R2`; `C-05`, live topology
  preflight `PF-05`.
- **Файли та зміни:** add per-task soft/hard limits and worker-lost policy in
  `app/workers/celery_app.py`; heartbeat/health checks for worker/beat in
  protected compose files; alert uses existing worker task heartbeat data.
- **Транзакція / БД / зовнішні ефекти:** operational only; alert after DB read;
  no business mutation.
- **Тести:** stuck task, soft/hard timeout, heartbeat stale/healthy, container
  health command, no false unhealthy during idle.
- **Rollout / rollback / legacy:** canary worker, measured limits, protected
  runtime review; rollback config while preserving durable work.
- **DoD / розблоковує:** long/stuck tasks are bounded and observable;
  розблоковує join `C-09`.

#### C-07 — Obsolete analytics schema cleanup

- **Мета / risk / залежності:** remove only proven orphan analytics storage;
  `R2`; `R1-10`, live inventory zero readers/writers.
- **Файли та зміни:** remove `DailyMetrics` model/repo/tests and add destructive
  Alembic revision for `daily_metrics`; update retention/catalog docs.
- **Транзакція / БД / зовнішні ефекти:** migration only; no runtime dual read.
- **Тести:** code search/architecture guard, migration upgrade from production
  predecessor and clean DB, admin/internal analytics regression.
- **Rollout / rollback / legacy:** backup/export if retention requires; separate
  reviewed migration; rollback by forward restore only, not automatic downgrade.
- **DoD / розблоковує:** zero caller and one analytics source/table family;
  розблоковує join `C-09`.

#### C-08 — Legacy delivery tables and audit-ledger naming

- **Мета / risk / залежності:** close `AR-018/028` leftovers; `R3`; every old
  delivery caller zero, nonterminal inventory resolved, `PF-05`.
- **Файли та зміни:** remove `deliver_telegram_once`, retry repos і
  `telegram_delivery_attempts` only when all rows terminal or explicitly
  classified; inventory `daily_push_logs` readers/retention and drop only after
  zero callers + approved disposition; never clone rows lacking payload.
  Physical `outbox_events` table remains the audit/manual-review ledger (no
  table rename); move Python-facing
  `app/db/models/outbox_events.py::OutboxEvent` and
  `app/db/repo/outbox_events_repo.py::OutboxEventsRepo` to
  `audit_event_ledger.py::AuditEventLedgerEntry` and
  `audit_event_ledger_repo.py::AuditEventLedgerRepo`, update all consumers and
  admin labels, then remove old exports.
- **Транзакція / БД / зовнішні ефекти:** destructive migration only after
  `q_delivery` is sole dispatcher; pending rows never discarded. Logical
  Python rename does not rewrite audit rows.
- **Тести:** zero-caller/old-symbol guard, production-shaped row inventory,
  migration, admin/replay/retention regression and all audit-review consumers.
- **Rollout / rollback / legacy:** mandatory separate data/ops review and
  backup; no DB downgrade. If one ambiguous row exists, defer table cleanup;
  logical audit-ledger rename may ship independently in the same PR before the
  guarded migration.
- **DoD / розблоковує:** no orphan retry infrastructure or dispatcher-like
  Python name; `daily_push_logs` has retained-or-dropped evidence and every
  historical row disposition is auditable; розблоковує `C-09`.

#### C-09 — Final debt ratchet, docs and configuration cleanup

- **Мета / risk / залежності:** close `AR-034`–`AR-039` remaining structural
  drift without rewrite; `R1`; joins `C-01`–`C-08`.
- **Файли та зміни:** ratchet already-correct cross-platform architecture/debt
  guards for deleted legacy edges; update
  `docs/architecture/current_runtime_map.md`, debt baseline, analytics/delivery
  runbooks; replace hardcoded Daily Cup bot share name with configured link;
  remove expired registry entries.
- **Транзакція / БД / зовнішні ефекти:** none.
- **Тести:** local/CI parity, docs/config contract, no stale flags/import edges;
  rerun Windows regressions created in `R1-04`; do not use line-count splitting
  as sole DoD.
- **Rollout / rollback / legacy:** docs/CI-only PR; protected CI review.
- **DoD / розблоковує:** active docs match runtime, all join milestones have
  evidence, registry empty або має only intentionally active entries; roadmap
  complete or safely pausable.

---

## 4. Dependency graph, pause points and reviews

### 4.1 Critical path

```text
R0-01 ─┐
R0-02 ─┼─> R0-03/R0-04 ─> Release 0 verified
       │
       └─> R1-01..R1-10 correctness/controls/cleanup
                         │
                         └─> S1-01 promo pilot
                                  │
                                  └─> S2-01/S2-02 Daily push boundary
                                           │
                                           └─> D3-01..D3-06 dispatcher
                                                    │
                                                    └─> D3-07/D3-08 pilot
                                                             │
                                                             └─> Referrals
                                                                  └─> Arena
                                                                       └─> Friend
                                                                            └─> Tournaments
                                                                                 └─> Payments
                                                                                      └─> Cleanup
```

Критичний технічний ланцюг усередині Slice 3:

```text
schema → claim/lease/CAS → provider adapter → q_delivery/repair
       → same-row replay → admin/metrics/alerts → pilot cutover → cleanup
```

### 4.2 Що можна робити паралельно

- `R0-01` і підготовку `R0-02` можна вести паралельно; production Release 0
  чекає `R0-01`–`R0-04`.
- Після Release 0 незалежні `R1-01`, `R1-02`, `R1-03`, `R1-04`,
  `R1-08`, `R1-09` можуть готуватися паралельно. `R1-05` залежить від
  architecture/CI contract, `R1-07` — від `R1-06`; Slice 1 чекає time-gated
  `R1-10`.
- Characterization tests наступного stage можна підготувати під час observation
  попереднього, але не створювати третій dual path і не перемикати runtime.
- У D3 schema/protocol PR reviews можуть перекриватися, але `q_delivery` не
  активується до replay, visibility й alerts.
- Pure payment/tournament decision tests можна ділити на окремі гілки, але
  fixed roadmap і один active behavioral migration зберігаються.

### 4.3 Safe pause points

- Після Release 0: security closed, architecture ще legacy.
- Після Release 1: correctness/operational truth closed; це повноцінний
  допустимий terminal state.
- Після `S1-01`: pilot pattern оцінений; якщо він не спростив код/tests,
  architecture roadmap зупиняється й ADR переглядається.
- Після `D3-08`: durable delivery infrastructure корисна сама по собі; major
  value/risk reassessment перед Arena/Friend/Tournaments.
- Після cleanup кожного Ref/Arena/Friend/Tournament/Payment stage.

Перед pause активний registry entry або закривається, або має чинні owner,
`review_by`, fallback metric і rollback value; pending durable rows мають
працюючий consumer/repair.

### 4.4 Runtime cutover points

| Cutover | Milestone | Обов’язковий gate |
|---|---|---|
| Canonical analytics reader | `R1-07` | documented definition, freshness, bounded comparison, rollback flag |
| Redis cooldown | `R1-09` | shared TTL/outage tests |
| First durable delivery | `D3-07` | `D3-01`–`D3-06` deployed together, visibility live |
| Referral mutations/notification | `REF-02/03` | zero pure-decision mismatch, dispatcher SLO |
| Arena | `A-03`–`A-08` | replay fixed, shadow evidence, staged slots, PostgreSQL concurrency |
| Friend | `F-02`–`F-05` | serialized caps, one workflow, staged delivery |
| Tournaments | `T-01`–`T-09` | per-item recovery, reward-before-proof, complete business cycle |
| Payments | `P-04`–`P-16` | staged app/reconciliation/refund, dry-run/shadow, review path |

### 4.5 Write-slot proof

Staged enum займає один slot лише якщо має один registry entry, рухається
монотонно, для кожного effect обирає рівно один route і не залишає hidden
boolean aliases.

| Phase | Slot 1 | Slot 2 | Gate before next phase |
|---|---|---|---|
| Release 1 | none; analytics route read-only | none | `R1-10` removes read flag |
| Durable pilot | `D3-07` Daily delivery | none | `D3-08` closes |
| Referrals | `REF-02` reward mutation | `REF-03` delivery | `REF-04` closes both |
| Arena | `A-03..A-05` access stage | `A-06..A-08` delivery stage | `A-09` closes both |
| Friend | `F-02` access stage | `F-03..F-05` delivery stage | `F-06` closes both |
| Tournament before `T-07` | `T-01` lifecycle | `T-02..T-06` delivery | `T-07` closes delivery |
| Tournament after `T-07` | `T-01` lifecycle | `T-08/T-09` finalization | `T-10` closes both |
| Payments before `P-12` | `P-04..P-08` application | none | adapters/shadow use no slot |
| Payments at `P-12` | application | reconciliation | `P-13` closes application |
| Payments after `P-13` | `P-14` refund | reconciliation | `P-17` closes both |
| Further cleanup | `C-02` incoming runtime route at most | none | `C-03` closes slot; `C-09` final join |

`telegram_stars_reconciliation_dry_run`, emergency kill switches і pure shadow
не є legacy/new writers (`occupies_write_slot: false`), але все одно мають
owner/deadline. Жодна строка timeline не має третього slot.

### 4.6 Mandatory separate reviews

- Release 0 security behavior and production verification.
- Every Alembic migration, especially partial indexes and destructive cleanup.
- Protected `.github/workflows/**`, `docker-compose.prod.yml`,
  `deploy/quiz-arena/docker-compose.prod.yml` and worker topology changes.
- Every R3 cutover and its shadow evidence.
- Any workflow with a fourth module, any sixth active workflow package, or any
  workflow calling another workflow — implementation is blocked pending ADR.
- Any proposed DB downgrade, deletion of nonterminal delivery state, change to
  refund/debt semantics, or auto-recovery enablement.

---

## 5. Cross-module atomic workflows

`app/workflows/` містить лише commands, для яких partial commit порушує названий
business invariant. Telegram/outgoing delivery саме по собі не робить operation
workflow: durable integration event у source transaction достатній.

### 5.1 `StartMeteredQuizSession` — gameplay + economy (доведений, deferred)

- **Invariant:** playable `QuizSession` існує разом із рівно одним дозволеним
  energy/premium access decision і, коли energy consumed, відповідним ledger
  debit; немає session без access result і debit без session.
- **Evidence:** `app/game/sessions/service/sessions_start.py` споживає access і
  створює session в одній SQL session; legacy
  `economy/energy/energy_consume_quiz.py` зараз змішує target gameplay-owned
  energy state з economy entitlement/ledger.
- **Чому event недостатній:** asynchronous authorization дозволив би overspend
  або playable session без оплати; compensation не повертає користувачу
  однозначний start result.
- **Порти:** `GameplaySessionEnergyPort.lock_energy_and_create_started_session`,
  `EconomyEntitlementLedgerPort.authorize_and_record_consumption`; один workflow
  transaction, energy не приписується economy module.
- **Roadmap:** не переносити в межах цього плану до окремо авторизованого later
  gameplay slice; зберігати current atomicity.

### 5.2 `CompleteDailyQuizWithReward` — gameplay + economy (чинний контракт, deferred)

- **Invariant:** terminal Daily result і негайно обіцяна ticket/energy reward
  commit-яться разом.
- **Evidence:** `sessions_submit.py`, `sessions_submit_daily.py`,
  `sessions_submit_daily_rewards.py`; bot text одразу повідомляє, що reward
  отримано.
- **Чому event недостатній:** без продуктового стану `reward pending`
  read-after-write UX і наступна дія очікують вже доступну reward.
- **Порти:** `DailyCompletionPort.complete`,
  `DailyRewardPort.grant_idempotently`.
- **Roadmap:** deferred; якщо `PF-09` дозволить explicit pending state,
  замінити workflow durable event-ом.

### 5.3 `CreateFriendChallengeWithAccess` — competitions + gameplay + economy

- **Invariant:** challenge з `FREE/PREMIUM/PAID_TICKET` створюється лише під
  серіалізованою перевіркою capacity; paid uses не перевищують credits.
- **Чому event недостатній:** authorization має передувати row commit;
  reserve/compensate лишає ticket без challenge або допускає over-capacity.
- **Порти:** `EconomyDuelAccessPort.lock_and_read_capacity`,
  `CompetitionChallengePort.lock_caps_and_create`,
  `GameplayQuestionPlanPort.build_immutable_plan`; Arena source може надати
  already-frozen question plan без нового gameplay mutation.
- **Використання:** workflow створюється в `A-05` для Arena revanche, а `F-02`
  додає regular direct/open variants; жоден workflow не викликає інший.

### 5.4 `CreateArenaDuelWithAccess` — competitions + gameplay + economy

- **Invariant:** baseline attempt/playable session і authorized Arena access
  виникають разом.
- **Порти:** `EconomyDuelAccessPort.lock_and_read_capacity`,
  `ArenaCreationPort.create_duel_and_attempt`,
  `GameplaySessionStartPort.create_started_session`.
- **Чому event недостатній:** partial commit створює unusable paid duel або
  consumes capacity без playable attempt.
- **Використання:** `A-03`.

### 5.5 `AcceptArenaDuelWithAccess` — competitions + gameplay + economy

- **Invariant:** challenger attempt/playable session і accept access capacity
  commit-яться разом.
- **Порти:** `EconomyDuelAccessPort.lock_and_read_capacity`,
  `ArenaAcceptancePort.create_challenger_attempt`,
  `GameplaySessionStartPort.create_started_session`.
- **Чому event недостатній:** asynchronous accept authorization може overspend
  або видати attempt, який потім треба компенсувати.
- **Використання:** `A-04`.

### 5.6 Що workflow не потребує

- Referral/Arena/friend/tournament notification, proof card і quota message:
  source transaction + durable integration event + idempotent dispatcher.
- Arena completion: current code не має economy reward; competition result і
  durable event достатні.
- Daily Cup rewards: current grant уже asynchronous after competition
  completion; immutable standings event + idempotent economy grant є safe
  default.
- Purchase/refund/entitlement/ledger/catalog: один bounded `economy` module.
- Analytics ніколи не є eligibility/quota authority.

### 5.7 Anti-god-module controls

- Один package — один business command і один transaction contract.
- Максимум три modules, no workflow chaining, no transport branching.
- Workflow бачить narrow ports, не repositories/ORM/global service locator.
- Rows/locks, idempotency, transaction duration і exact invariant документовані
  в package README/test.
- Edges allowlisted architecture tool-ом.
- Четвертий module блокує PR; пропозиція шостого active workflow package
  запускає boundary review. П’ять перелічених вище є абсолютною верхньою межею
  без нового ADR.

---

## 6. Delivery migration protocol

Одна `outgoing_deliveries` table навмисно обслуговує два closed
`dispatch_kind`: `TELEGRAM` і `INTERNAL_HANDLER`. Для Telegram
`recipient_key` обов’язковий; для internal handler він `NULL`, а
`provider_message_id` не використовується. Перші internal types рівно два:

- `tournament.round_messaging_requested.v1`;
- `daily_cup.final_standings.v1`.

Кожний type має compile-time explicit handler у
`app/bootstrap/outgoing_effect_handlers.py`. Dynamic registration/discovery,
arbitrary choreography, workflow chaining і окремий event service відсутні.
Unknown type є terminal configuration error. Новий type потребує окремого
milestone, versioned payload contract, architecture allowlist і failure-window
tests. Source modules імпортують лише `messaging.public` і викликають
session-bound `OutgoingEffectWriterPort`; конкретний writer не володіє
transaction.

### 6.1 Введення `q_delivery`

1. Additive `outgoing_deliveries` schema deploy-иться без producers.
2. Claim/CAS/provider tests проходять на PostgreSQL.
3. Existing Celery worker починає слухати
   `q_delivery,q_high,q_normal,q_low`; prefetch `1`; нового process немає.
4. Beat scanner кожні 5 секунд, batch ≤50, single-run advisory guard.
5. Immediate post-commit `dispatch_outgoing_row(id)` є лише wakeup; scanner є
   correctness path.
6. Admin/replay/metrics/alerts deploy-яться до першого producer cutover.

### 6.2 Claim/lease/CAS

```text
PENDING/RETRY (due)
  -- short tx, SKIP LOCKED, token, lease, attempt++ -->
CLAIMED
  -- Telegram adapter або explicit internal handler outside claim tx -->
  SENT | RETRY(next_retry_at) | FAILED | SKIPPED
```

- Outcome update має `WHERE id/status/claim_token`.
- Expired `CLAIMED` отримує новий token; старий worker більше не може mark-нути
  outcome.
- Heartbeat потрібний лише для реально довгого provider/render effect; lease
  не продовжується без bound.
- Backoff bounded exponential + jitter, `RetryAfter` honored, max attempts/age
  explicit per effect class.
- Для internal effect `SENT` означає successful receiver commit. Crash після
  receiver commit, але до parent `SENT`, повторює handler; receiver зобов’язаний
  мати business idempotency key і не повторювати grant/mutation.

### 6.3 Replay

- Лише audited CAS `FAILED|SKIPPED → RETRY`.
- Той самий row, payload version і `idempotency_key`.
- `SENT` і active `CLAIMED` не replay-яться.
- Replay не повторює source reward/debit/quota mutation.
- Wakeup failure після replay не губить work — scanner побачить `RETRY`.

### 6.4 Visibility and SLO

Admin показує state counts, oldest due, stale claims, attempts, bounded error
class, last success, provider id, source correlation і replay audit. Safe
default: read — `admin`; replay/suppress — `super_admin`.

Operational source of truth — PostgreSQL. Redis queue depth показує тільки
transport backlog. Initial targets:

- critical p95 claim latency <5s;
- critical due row >30s — alert;
- backlog >100 протягом 5 хв — alert;
- stale lease, terminal failure і replay actions — окремі metrics/audit.

### 6.5 Gradual switching

- Один flow на PR, routing mutually exclusive.
- Presenter/internal handler map і unknown-type acceptance test deploy-яться до
  producer flag для кожного нового `effect_type`.
- Shadow only recipient/payload canonical digest, never send.
- Daily push → referral notification → Arena/friend → tournament batches.
- `telegram_delivery_attempts` і `deliver_telegram_once` лишаються лише для
  unmigrated callers; нові flows їх не використовують.
- `outbox_events` не використовується як dispatcher.

### 6.6 Rollback without losing pending work

- Flag stops creation of new outgoing rows for that flow.
- `q_delivery` consumer/repair продовжує drain all existing
  `PENDING/CLAIMED/RETRY`.
- Additive table/indexes не downgrade-яться.
- Legacy selector тимчасово бачить existing outgoing key, щоб rollback не
  створив duplicate.
- Якщо sender треба emergency-stop, rows лишаються nonterminal і resume-яться;
  вони не переводяться bulk у terminal state.
- Старі attempt rows без payload не clone-яться автоматично.

---

## 7. Testing, rollout and cleanup contract

### 7.1 Common sequence

1. Characterize current visible behavior and DB outcomes.
2. Separate preserved behavior, intentional bug fix and product-policy change.
3. Add framework-free application tests.
4. Add only relevant real-adapter/PostgreSQL tests.
5. Deploy additive code/schema disabled when flag required.
6. Run pure shadow where technically valid.
7. Internal/admin → deterministic cohort → full cutover.
8. Observe for tier window and full business cycle.
9. Separate cleanup PR deletes legacy/flag/tests/registry; schema later.

### 7.2 R1

- Focused characterization and application test.
- One real entrypoint/adapter test.
- One PostgreSQL happy path only when DB mutation exists; PostgreSQL-specific
  semantics still require real DB test.
- No flag/shadow unless rollback cannot be a safe route/config/git revert.
- Legacy removed immediately after equivalence.

### 7.3 R2

- R1 checks plus every relevant lock/conflict/idempotency case.
- Applicable commit/provider failure windows and one real FastAPI/aiogram/Celery
  path.
- Server-side explicit flag unless simpler rollback is demonstrated.
- State/error metrics.
- Cleanup after ≥7 stable full-cutover days; unexpected fallback/rollback
  restarts the window.

### 7.4 R3

- Every material PostgreSQL race/recovery and crash point.
- Additive schema, explicit flag, durable effect/operator visibility where
  relevant.
- Forward-only security/correctness fix з unsafe legacy fallback (`R0`,
  `R1-01/02/03`, `A-01`, `F-01`, `P-01`, `C-04`) не отримує штучного
  flag/shadow: direct fix зберігає повний R3 test rigor, а rollback є лише safe
  forward fix або operational stop, не повернення vulnerability/invariant gap.
- Pure shadow stored in `architecture_shadow_comparisons` only for comparable
  decisions; zero mismatch default for money, entitlement, reward, quota and
  invariant decisions.
- Store canonical digest, hashed correlation, bounded difference code/context;
  no raw Telegram payload, payment token, TOTP, secret або unnecessary PII;
  detail retention 30 days.
- Cutover requires slice-specific minimum sample and business cycle.
- Cleanup after ≥14 stable days plus one full relevant business cycle.
- Audited replay/suppress and alerts for ambiguous/stuck/failed state.

### 7.5 Registry and two-path limit

- Every legacy/new pair is present before merge з ADR fields `created_at`,
  `review_by`, `removal_condition`, `legacy_usage_metric`, owner і rollback.
- `occupies_write_slot: true` означає, що legacy і new mutation/send writers
  співіснують за mutually exclusive router; це ніколи не означає simultaneous
  dual write/send.
- Один flag/staged enum selects exactly one writer per behavior. Staged enum є
  одним slot лише за умов із §4.5.
- Validator hard-fail-ить expired deadline, missing required field,
  orphan/unwired setting, deleted entrypoint, hidden alias або third active
  write slot. Historical warning exception після `R1-05` відсутній.
- Зміна `review_by` дозволена лише append-only amendment із old/new date,
  reason, approval time та owner; silent extension hard-fail-иться.
- Read-only reader switch, kill switch і pure shadow мають
  `occupies_write_slot: false`, але не звільняються від owner/deadline/cleanup.
- Другий slot може бути fully-cut-over path, що очікує observation cleanup; до
  його закриття третій не стартує.
- `DUELS_ROLLOUT_ENABLED` must be inventoried/classified; default `true` does
  not silently exempt it from governance.

---

## 8. Open preflight checks

Тут лишені лише питання, відповідь на які неможливо достовірно отримати з
repository snapshot.

| ID | Що перевірити / як | Блокує | Safe default |
|---|---|---|---|
| `PF-01` | Хто є production authority для admin enabled/disabled, email і role: config чи DB? Звірити operator policy, deployed env і admin inventory. | `R0-03` production DoD | Deny missing/mismatch; ніколи не auto-create/update з JWT claim. |
| `PF-02` | Чи є duplicate `IN_PROGRESS` DailyRun на `(user_id, berlin_date)`? Read-only production SQL, визначити deterministic survivor/repair. | `R1-03` migration | Не створювати index і не delete-ити data до approved repair. |
| `PF-03` | Product/operator definition DAU/WAU/MAU, timezone/freshness, supported `7d/30d/90d` comparisons і чи існує complete immutable source для historical backfill. Затвердити metric catalog та source-completeness proof із dashboard/data owner. | `R1-06/07` cutover | Не backfill-ити з mutable `User.last_seen_at`. Додати `user_activity_days`, позначити old rows invalid і, якщо немає independently proven source, чекати prospective 120-day horizon before all-period reader cutover. |
| `PF-04` | Daily push SLA/effect class: ephemeral чи recoverable? Product/incident review. | `D3-07` effect contract | Recoverable `R2`; до dispatcher лише log-after-success, без гарантії retry. |
| `PF-05` | Live counts/age/errors у `telegram_delivery_attempts`, queue depths, worker/beat topology, applied migration head і p95 latency. Read-only DB/Redis/deployment inspection. | `D3-04/07`, `C-02`, `C-06`, `C-08` cutovers | Existing shared worker, no fifth process; no legacy row migration/deletion; no cutover без measured capacity. |
| `PF-06` | Дозволений outgoing content та мінімальний replayable incoming Telegram payload, encryption/key rotation і retention. Security/privacy review exact fields, recipient identifiers і incident access. | `D3-01`, `C-01/C-02` | Outgoing: template/type/version + bounded scalar args, no rendered text/secrets, 30-day detail. Incoming: encrypted versioned envelope, hash, no raw logs, purge terminal ciphertext after 7 days; C runtime cutover blocked until approved replay schema/key. |
| `PF-07` | Для кожного behavioral R3 slice: minimum shadow sample, “full business cycle” і owner approval. Записати в registry before rollout. | Кожний R3 runtime cutover, крім перелічених у §7.4 direct forward-only fixes | Cutover blocked; mismatch threshold zero for money/reward/quota/invariants. Forward-only fixes застосовують R3 tests, але не чекають synthetic shadow sample/cycle. |
| `PF-08` | Product semantics: різниця `new_users_only`/`first_purchase_only`, чи REFUNDED рахується paid history, Telegram Stars auto-recovery authority і будь-яка майбутня debt/collection policy. Product + finance/ops review. | `P-02`, `P-10/P-12` та лише policy-changing amendment після safe-default `P-14` | `P-14` не блокується: preserve current full financial reversal, claw back only available asset, report unrecovered amount, no debt state. Reconciliation stays dry-run; policy change потребує окремого milestone/flag. |
| `PF-09` | Чи Daily Quiz reward може бути explicit `pending` замість immediate? Product UX/terms review. | Deferred `CompleteDailyQuizWithReward` design | Preserve current atomic completion+reward workflow. |
| `PF-10` | Actual branch protection/CI required checks і authorization для protected runtime/CI files. Перевірити GitHub/deployment control plane before PR. | Merge/cutover milestones that touch protected files | Separate reviewed approval; do not bypass checks or edit production topology silently. |
| `PF-11` | Чи Friend/Arena push quota рахує business attempt, accepted outgoing row чи successful provider delivery? Звірити product policy, incident history і operator expectation. | `A-08`, `F-03` quota cutovers | Provider failure не ставить terminal delivered marker і не permanently consume-ить delivery quota; attempt accounting, якщо потрібне, зберігати окремо. |

---

## 9. Milestone inventory

- Загалом: **80** PR-sized milestones.
- `R1`: **3**.
- `R2`: **21**.
- `R3`: **56**.
- Blocking preflight records: **11**, але вони блокують лише вказані
  milestones/cutovers; `PF-01` є першим early blocker.

Цей count є planning baseline. Milestone можна додатково split-нути, якщо PR
перевищує один reviewable behavior, але не можна merge-нути security fix,
architecture transfer, нову DB state machine і legacy deletion в один PR.
