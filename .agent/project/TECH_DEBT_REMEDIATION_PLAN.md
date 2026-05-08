# TECH_DEBT_REMEDIATION_PLAN

Цей документ є активним project-specific планом для задач про:

- технічний борг;
- cleanup / stabilization;
- quality gates;
- refactor для доведення репозиторію до чистого стану;
- structural audit follow-up.

Якщо користувач просить зменшити техборг або "привести репо до ладу",
агент має працювати за цим планом, якщо користувач явно не задав інший
порядок.

## 1. Baseline and current snapshot

Базова точка для цього плану: аудит репозиторію станом на `2026-04-15`.
Поточне уточнення scope: аудит локального backend repo станом на
`2026-05-08`.

Початкові проблеми з базового аудиту:

- `High`: admin auth token revocation має fail-open поведінку при
  недоступності Redis (`app/services/admin/auth.py`).
- `High`: frontend lint/build вже падали локально в тодішньому repo layout;
  цей пункт superseded для backend repo після split у standalone frontend
  repo.
- `Medium`: `18` Python-файлів у `app/` перевищують `220` рядків; `1`
  файл перевищує `250`.
- `Medium`: `96` production functions/methods довші за `60` рядків.
- `Medium`: frontend мав великі client/page файли без test layer; цей
  пункт тепер належить standalone frontend repo.
- `Medium`: `mypy` покладається на `ignore_errors = true` для `tests.*`
  і частини складних app-модулів.
- `Low`: є drift між project docs і фактичним frontend/backend split.

Поточний стан локального backend repo на `2026-05-08`:

- `frontend/` у робочому дереві відсутній.
- Frontend source, frontend CI, and frontend image publishing live in the
  standalone repo `https://github.com/Valerii-S84/quiz-arena-frontend`.
- This backend repo still owns compose/proxy orchestration for consuming the
  published frontend runtime image via `FRONTEND_IMAGE`.
- Frontend findings from the original audit are superseded for this repo and
  must be handled in the standalone frontend repo, not by recreating local
  `frontend/` assumptions here.
- Admin auth fail-open finding is remediated in code: token decode
  depends on Redis-backed revoke state and raises `AdminAuthStateError` when
  auth state is unavailable; route dependencies map that state to HTTP 503.
- Targeted admin auth tests passed locally (`45 passed`).
- Full backend local CI passed on `2026-05-08` via `bash scripts/local_ci.sh`.
- Backend structural debt remains: `18` app files above `220` lines and
  `108` production functions/methods above `60` lines.
- `mypy` is green, and no `ignore_errors = true` override for production
  `app` modules was found in `pyproject.toml`.
- Test-suite structural debt remains limited to
  `tests/game/test_sessions_start_arena.py` above `400` lines.

## 2. Definition of clean state

Репозиторій вважається приведеним до чистого стану тільки якщо:

- не лишилося відкритих `High`-severity проблем із базового аудиту, які
  належать цьому backend repo;
- mandatory local gates проходять для backend;
- frontend source/CI/image publishing debt не дублюється в цьому repo і
  відстежується окремо в `quiz-arena-frontend`;
- GitHub CI покриває активну частину цього repo: Python backend;
- security-критичні flow не мають fail-open поведінки без явного,
  затвердженого compensating control;
- structural debt зменшений до керованого рівня, а не лише заморожений;
- документація і toolchain не суперечать фактичному стеку;
- новий борг не додається швидше, ніж закривається старий.

Практичний критерій "керованого рівня":

- `app/` не має production-файлів понад `220` рядків без явного
  погодженого винятку;
- production functions/methods довші за `60` рядків відсутні або
  лишаються тільки в явно задокументованому short exception list;
- `mypy` не має `ignore_errors = true` для production app-пакетів;
- backend test modules понад `400` рядків відсутні або розбиті за
  сценаріями.

## 3. Execution protocol

Агент має виконувати cleanup тільки в такому режимі:

- спочатку закривати blocking defects і security debt;
- не змішувати feature work з debt-remediation в одному PR/branch;
- не брати більше одного великого workstream за раз;
- не починати наступну фазу, поки попередня не має доказової перевірки;
- робити зміни малими серіями з чітким rollback surface;
- перед refactor спочатку фіксувати або додавати regression coverage там,
  де це реально потрібно для безпечної декомпозиції.

Project boundaries, які не можна ігнорувати:

- зміни в `.github/workflows/**` вимагають явного підтвердження
  користувача;
- deploy/runtime config, production paths, `.env*`, `deploy/**`,
  `docker-compose.prod.yml` не чіпати без окремого дозволу;
- міграції й data backfills не включати в cleanup з власної ініціативи.

## 4. Work order

Порядок фаз є обов'язковим, якщо користувач явно не змінив пріоритет.

### Phase 0. Align repo scope and active docs

Мета:

- прибрати stale локальні frontend припущення з active agent context;
- зробити так, щоб backend repo мав чесний green/red сигнал без вимоги
  неіснуючого `frontend/`.

Обов'язкові задачі:

- оновити `.agent/project/PROJECT_CONTEXT.md` під фактичний backend repo
  scope;
- оновити `.agent/project/CODE_STYLE.md` так, щоб він не вимагав
  `cd frontend && ...` у цьому repo;
- оновити цей remediation plan так, щоб frontend work було явно винесене в
  standalone repo scope;
- не змінювати `.github/workflows/**` без окремого підтвердження.

DoD фази:

- active project docs не посилаються на локальний `frontend/` як source tree;
- required local gates відповідають фактичному backend repo;
- frontend debt не пріоритизується в цьому repo як локальна робота.

### Phase 1. Close security and auth-state debt

Мета:

- прибрати fail-open поведінку в admin auth;
- зробити auth-state outage явним, контрольованим і тестованим.

Обов'язкові задачі:

- перепроєктувати перевірку revoked tokens так, щоб outage state-store не
  виглядав як "token is valid";
- окремо переглянути refresh/logout/TOTP flows при недоступності Redis;
- додати tests на Redis outage для access token, refresh token, logout і
  2FA-related flow;
- зменшити size/complexity `app/services/admin/auth.py` під час цієї
  роботи, якщо це потрібно для безпечного fix.

DoD фази:

- revoke/refresh/validation semantics чітко визначені;
- outage не призводить до fail-open авторизації;
- regression tests покривають degraded-state сценарії.

Поточний статус:

- Closed for this backend repo.
- Full backend local CI proof: `bash scripts/local_ci.sh` passed on
  `2026-05-08`.

### Phase 2. Stabilize structure in hottest backend zones

Мета:

- прибрати найдорогіші для підтримки Python-моноліти;
- зменшити довжину orchestration-функцій у критичних потоках.

Перший пріоритет:

- `app/bot/handlers/gameplay_duels.py`
- `app/db/repo/analytics_mutations.py`
- `app/game/sessions/service/friend_challenges_manage.py`
- long orchestration functions:
  `app/bot/handlers/gameplay_flows/answer_flow.py::handle_answer`,
  `app/workers/tasks/friend_challenges_async.py::run_friend_challenge_deadlines_async`,
  `app/bot/handlers/gameplay_flows/friend_answer_flow.py::handle_friend_answer_branch`

Правило декомпозиції:

- розділяй query access, domain decisions, rendering/text building,
  side-effects і framework entrypoints;
- не переносити в "utils" без чіткої ролі;
- не робити cosmetic split без зменшення відповідальності.

DoD фази:

- top oversized backend files або зменшені до цільових меж, або розбиті на
  тематичні модулі;
- top long functions більше не концентрують кілька рівнів абстракції;
- refactor підтверджений релевантними тестами.

Поточний статус:

- `app/workers/tasks/friend_challenges_notifications.py` розділено на
  orchestration, notification content і delivery modules; primary file
  зменшено до `80` рядків, нові modules лишаються нижче `220` рядків.

### Phase 3. External frontend remediation handoff

Мета:

- не виконувати frontend cleanup у цьому backend repo;
- не відновлювати локальний `frontend/` як side effect cleanup;
- залишити явний handoff для standalone repo.

Перший пріоритет:

- Аудит і cleanup standalone repo `quiz-arena-frontend`.

Обов'язкові задачі:

- не запускати `cd frontend && ...` у цьому repo;
- не додавати frontend source або frontend toolchain у цей repo без
  окремого explicit scope;
- якщо користувач просить frontend debt, переключити роботу на standalone
  frontend repo.

DoD фази:

- backend repo docs не містять stale локальних frontend інструкцій;
- standalone frontend debt не маскується як закритий у backend repo.

### Phase 4. Remove type-safety blind spots

Мета:

- зробити green `mypy` доказовим, а не умовним.

Обов'язкові задачі:

- прибирати `ignore_errors = true` з production app-модулів по одній
  зоні за раз;
- зменшувати `type: ignore` до вузьких, пояснених випадків;
- заміняти неявні `Any` і сирі `cast(...)` там, де можна описати реальний
  контракт типами;
- only after production cleanup переходити до `tests.*`.

DoD фази:

- `ignore_errors = true` для app-пакетів відсутній;
- найбільш ризикові flows мають реальні типові контракти;
- `mypy` лишається green без широких винятків.

### Phase 5. Split oversized tests and fixtures

Мета:

- зменшити вартість підтримки test suite;
- зробити regression signals локальними і читабельними.

Обов'язкові задачі:

- розбити test files понад `400` рядків за сценаріями або піддоменами;
- винести повторюваний setup у зрозумілі fixtures/helpers;
- не ховати логіку в складних fixtures, якщо це робить тест менш ясним.

DoD фази:

- test files більше не є сценарними монолітами;
- назва тесту і його setup швидко читаються без deep scrolling;
- coverage для refactored flows збережений або покращений.

## 5. PR slicing rules

Якщо cleanup виконується серією PR/гілок, використовуй такий порядок:

1. active backend repo docs/scope alignment
2. admin auth full backend CI proof
3. backend monolith split by hotspot
4. mypy cleanup by domain, only if production blind spots are found
5. oversized test split
6. external frontend remediation in `quiz-arena-frontend`, if requested in
   that repo scope

У кожному PR має бути тільки один з цих результатів або одна дуже вузька
частина фази.

## 6. Required proof per phase

Backend-focused зміни:

- `ruff check app tests`
- `black --check app tests`
- `isort --check-only app tests`
- `mypy app tests`
- `pytest -q --ignore=tests/integration`

Frontend-focused зміни:

- Not applicable in this backend repo.
- For standalone frontend work, use that repo's own active rules and gates.

Flow-sensitive або infra-sensitive зміни:

- `bash scripts/local_ci.sh`, коли зміни торкаються runtime boundaries,
  integration contracts або CI-equivalent expectations

## 7. Anti-regression rules

Поки cleanup план не закрито, агенту заборонено:

- додавати нові large files у проблемних зонах;
- розширювати `ignore_errors = true` або множити `type: ignore`;
- додавати нові broad `except Exception` без вузько поясненої причини;
- переносити складність у "helper"/"utils" файли без доменної ролі;
- додавати локальний frontend toolchain/source у backend repo без explicit
  frontend reintegration scope.

## 8. Completion condition for the whole plan

План можна вважати закритим тільки якщо:

- Phase 0-5 завершені для цього backend repo або явно superseded новим
  затвердженим планом;
- repo має green backend gates;
- backend-owned audit findings від `2026-04-15` більше не актуальні;
- новий агент може почати роботу без прихованого cleanup контексту.
