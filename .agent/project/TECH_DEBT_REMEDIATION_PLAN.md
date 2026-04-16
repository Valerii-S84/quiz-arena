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

## 1. Baseline audit snapshot

Базова точка для цього плану: аудит репозиторію станом на `2026-04-15`.

Підтверджені проблеми:

- `High`: admin auth token revocation має fail-open поведінку при
  недоступності Redis (`app/services/admin/auth.py`).
- `High`: frontend lint/build вже падають локально, але frontend не
  покритий GitHub CI.
- `Medium`: `18` Python-файлів у `app/` перевищують `220` рядків; `1`
  файл перевищує `250`.
- `Medium`: `96` production functions/methods довші за `60` рядків.
- `Medium`: frontend має великі client/page файли без test layer
  (`promo-client.tsx`, `app/(public)/page.tsx`).
- `Medium`: `mypy` покладається на `ignore_errors = true` для `tests.*`
  і частини складних app-модулів.
- `Low`: є drift між project docs і фактичним стеком frontend
  (`PROJECT_CONTEXT.md` каже `Next.js 14`, фактично використовується
  `Next.js 15.5.14`).

## 2. Definition of clean state

Репозиторій вважається приведеним до чистого стану тільки якщо:

- не лишилося відкритих `High`-severity проблем із базового аудиту;
- mandatory local gates проходять для backend і frontend;
- GitHub CI покриває обидві активні частини репозиторію:
  Python backend і Next.js frontend;
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
- frontend не має page/client файлів понад `500` рядків;
- `mypy` не має `ignore_errors = true` для production app-пакетів;
- frontend має хоча б базовий automated test layer для критичних flows.

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

### Phase 0. Restore green gates

Мета:

- прибрати поточні blocking failures у frontend;
- зробити так, щоб repo мав чесний green/red сигнал.

Обов'язкові задачі:

- виправити поточний lint/build blocker у `frontend/app/(public)/page.tsx`
  (`<a href="/">` -> `Link`);
- перевірити, що `npm run lint` і `npm run build` проходять локально;
- винести frontend lint/build у CI або інший mandatory protected gate;
- якщо для цього треба міняти `.github/workflows/**`, спочатку Ask First.

DoD фази:

- frontend lint проходить;
- frontend production build проходить;
- frontend не лишається поза mandatory gate.

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

### Phase 2. Stabilize structure in hottest backend zones

Мета:

- прибрати найдорогіші для підтримки Python-моноліти;
- зменшити довжину orchestration-функцій у критичних потоках.

Перший пріоритет:

- `app/services/admin/auth.py`
- `app/bot/handlers/gameplay.py`
- `app/bot/handlers/gameplay_flows/friend_answer_completion_flow.py`
- `app/api/routes/admin/overview_queries.py`
- `app/game/sessions/service/progression.py`
- oversized worker/tasks modules around daily cup, tournaments, proof cards

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

### Phase 3. Decompose frontend and add safety net

Мета:

- прибрати frontend single-file concentration;
- додати базовий test layer для критичних UI flows.

Перший пріоритет:

- `frontend/app/(admin)/admin/(secure)/promo/promo-client.tsx`
- `frontend/app/(public)/page.tsx`

Обов'язкові задачі:

- розділити data-fetching hooks, formatting helpers, modal/view components
  і page shell;
- не лишати data orchestration, form state, modal rendering і table logic в
  одному giant component;
- додати frontend test runner і мінімальний coverage для:
  public home navigation,
  admin login entry,
  promo create/edit/bulk happy path.

DoD фази:

- ключові frontend файли розбиті на читабельні модулі;
- `frontend` має test command у package scripts;
- критичні flows мають автоматизовану перевірку.

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

### Phase 6. Eliminate documentation and tooling drift

Мета:

- синхронізувати агентський і runtime контекст із фактичним станом репо.

Обов'язкові задачі:

- оновити project docs під фактичні версії Next.js / React / lint flow;
- замінити deprecated `next lint` flow на актуальний ESLint CLI path;
- прибрати або заархівувати stale planning docs, якщо вони заважають
  onboarding або вводять в оману;
- не змінювати historical archive без потреби.

DoD фази:

- docs не суперечать фактичному стеку;
- локальні команди збігаються з реально підтримуваним toolchain;
- onboarding не залежить від застарілих припущень.

## 5. PR slicing rules

Якщо cleanup виконується серією PR/гілок, використовуй такий порядок:

1. frontend red -> green
2. frontend gate in CI
3. admin auth fail-open fix
4. admin auth decomposition
5. backend monolith split by hotspot
6. frontend promo decomposition
7. frontend test layer
8. mypy override removal by domain
9. oversized test split
10. docs/tooling drift cleanup

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

- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- frontend tests, якщо test runner вже доданий

Flow-sensitive або infra-sensitive зміни:

- `bash scripts/local_ci.sh`, коли зміни торкаються runtime boundaries,
  integration contracts або CI-equivalent expectations

## 7. Anti-regression rules

Поки cleanup план не закрито, агенту заборонено:

- додавати нові large files у проблемних зонах;
- розширювати `ignore_errors = true` або множити `type: ignore`;
- додавати нові broad `except Exception` без вузько поясненої причини;
- переносити складність у "helper"/"utils" файли без доменної ролі;
- залишати frontend без green lint/build після будь-яких frontend змін.

## 8. Completion condition for the whole plan

План можна вважати закритим тільки якщо:

- Phase 0-6 завершені або явно superseded новим затвердженим планом;
- repo має green backend і frontend gates;
- базові audit findings від `2026-04-15` більше не актуальні;
- новий агент може почати роботу без прихованого cleanup контексту.
