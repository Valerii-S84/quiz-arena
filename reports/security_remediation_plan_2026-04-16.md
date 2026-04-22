# План закриття підтверджених security-gap findings (2026-04-16)

## Scope

Цей документ покриває тільки 5 підтверджених прогалин із поточного security-аудиту:

1. секрети потрапляють у Docker build context через відсутність `.env*` у `.dockerignore`;
2. admin rate limit живе в пам'яті процесу і не є shared між worker-процесами;
3. публічний `/contact` / `/api/contact` не має anti-abuse контролів;
4. ops cookie є replayable bearer, похідним від `INTERNAL_API_TOKEN`;
5. публічний `/health` розкриває внутрішній operational state.

План навмисно не розширюється на інші знайдені проблеми, навіть якщо вони суміжні.

## Порядок виконання

Порядок фаз обраний за принципом:

1. спочатку прибрати найнебезпечніший витік секретного surface з найменшим rollback surface;
2. потім розрізати internal/ops trust boundary;
3. потім зробити brute-force control shared і доказовим;
4. потім закрити public abuse surface;
5. в кінці мінімізувати зовнішній operational leakage.

## Глобальні правила виконання

- Працювати малими слайзами; кожен слайз має залишати repo у консистентному стані.
- Не змішувати дві фази в одному PR.
- Усередині фази не розносити тести по кожному слайзу: тестовий блок виконується в кінці фази.
- Не читати і не друкувати реальні `.env*`.
- Будь-які зміни в `deploy/**`, `docker-compose.prod.yml`, `.env*`, secret templates або нові зовнішні anti-bot сервіси вимагають окремого явного підтвердження перед виконанням.
- Якщо під час реалізації фази доведеться міняти `.github/workflows/**`, це теж окремий approval gate.

## Матриця фаз

| Фаза | Закриває finding | Пріоритет | Protected-path / approval gate |
|---|---|---|---|
| 1 | Docker build context + `.env*` leakage | High | Ні, якщо вистачає `.dockerignore` + локального test helper |
| 2 | replayable ops cookie / змішаний internal auth | High | Ні, якщо без `.env*` / external deps |
| 3 | per-worker admin rate limit | Medium | Ні, якщо використовується наявний Redis |
| 4 | public contact anti-abuse | Medium | Так, якщо буде потрібен captcha/external provider |
| 5 | public health leakage | Low | Так, бо майже напевно зачіпає `deploy/Caddyfile` |

## Phase 1. Docker Build Context Hardening

### Мета

Прибрати потрапляння `.env`, `.env.backup_*` та інших secret-like артефактів у Docker build context для backend image build.

### Цільовий результат фази

- build context більше не включає `.env*` і backup-файли;
- root image продовжує збиратися без зміни бізнес-логіки;
- у repo є явна перевірка, яка не дає випадково прибрати ці інваріанти.

### Slice 1.1. Зафіксувати allowlist/denylist для build context

- Переглянути всі `COPY` у root [Dockerfile](/mnt/c/Users/User/Desktop/Quiz Arena/Dockerfile:1) і явно підтвердити, що build використовує allowlisted `COPY`, а не `COPY . .`.
- Оновити root `.dockerignore` так, щоб у build context не потрапляли:
  - `.env`
  - `.env.*`
  - `.env.backup_*`
  - інші backup/env-похідні, якщо вони відповідають локальним naming patterns
- Не робити винятків для example env-файлів, якщо build їх фактично не використовує.

### Slice 1.2. Закріпити інваріант у репозиторії

- Додати невелику repo-local перевірку інваріанта:
  - або shell-скрипт у `scripts/`,
  - або backend test, який перевіряє, що `.dockerignore` містить required denylist patterns.
- Перевірка має бути narrowly scoped саме на build-context secret exclusion, без розростання до великого policy engine.

### Slice 1.3. Перевірити, що hardening не ламає build surface

- Зібрати backend image після зміни `.dockerignore`.
- Окремо перевірити, що frontend build surface не зачеплено.
- Не торкатися `docker-compose.prod.yml`, якщо ця фаза закривається тільки `.dockerignore`.

### Тести в кінці фази

- Статична перевірка інваріанта `.dockerignore`.
- `docker build -f Dockerfile .`
- `docker build -f frontend/Dockerfile frontend`
- Додатковий repo hygiene check:
  - `git ls-files '.env*'`
  - очікування: tracked лишаються лише example-файли.

### Exit criteria фази

- `.env*` і backup env-файли не входять у Docker build context;
- backend/frontend build smoke проходить;
- інваріант зафіксований у коді або в test helper, а не лише в документі.

## Phase 2. Internal/Ops Auth Boundary Hardening

### Мета

Розділити machine-token auth і browser-session auth, прибрати похідний від `INTERNAL_API_TOKEN` cookie і зробити ops session окремою, revocable та непридатною як replayable substitute для internal token.

### Цільовий результат фази

- browser cookie більше не є `sha256(INTERNAL_API_TOKEN)`;
- internal service auth і ops browser auth мають окремі контракти;
- logout та session expiry реально відкликають доступ;
- внутрішні маршрути не покладаються на blanket fallback із shared helper.

### Slice 2.1. Розвести auth API за типами клієнтів

- Розбити поточний shared helper із [internal_auth.py](/mnt/c/Users/User/Desktop/Quiz Arena/app/services/internal_auth.py:1) на окремі перевірки:
  - service-to-service auth через `X-Internal-Token`;
  - browser ops session auth через окремий session validator;
  - helper для IP allowlist лишити shared тільки там, де це реально спільна логіка.
- Прибрати загальний pattern "header token OR ops cookie" з одного універсального guard.

### Slice 2.2. Замінити cookie на opaque server-side session

- На логіні `/ops/login` перестати класти в cookie похідне від `INTERNAL_API_TOKEN`.
- Замість цього:
  - генерувати випадковий opaque session id;
  - зберігати session state server-side у Redis;
  - у cookie тримати тільки opaque id або signed opaque reference;
  - прив'язати TTL до поточного ops session lifetime.
- Logout має видаляти session state, а не лише cookie у браузері.

### Slice 2.3. Обмежити, де саме приймається ops session

- В ops routes використовувати тільки ops-session validator.
- Для `/internal/*` маршрутів явно визначити режим:
  - або лише `X-Internal-Token` для машинних викликів;
  - або окремо дозволяти ops session тільки там, де ці internal endpoints реально є backend surface для ops UI.
- Якщо ops UI продовжує ходити в `/internal/*`, зробити це через окремий explicit dependency, а не через загальний auth fallback.

### Slice 2.4. Закріпити degraded-state semantics

- Якщо Redis/state store недоступний, ops session validation не має перетворюватися на bypass.
- Для login/logout/session-check semantics має бути явний результат:
  - або `503 auth/session state unavailable`,
  - або інший контрольований fail-closed контракт.
- Не вводити нові env/secrets без окремої потреби; якщо новий secret все ж потрібен, ця підзадача блокується до окремого approval.

### Тести в кінці фази

- Targeted backend tests на:
  - login -> session issuance;
  - access with valid ops session;
  - logout -> session revoked;
  - expired session rejected;
  - random/forged cookie rejected;
  - replay of old `sha256(INTERNAL_API_TOKEN)` більше не автентифікує.
- Regression tests на internal routes:
  - machine token path працює;
  - ops session допускається тільки там, де це явно задумано.
- Загальний backend gate:
  - `make lint && make format-check && make type-check`
  - `pytest -q --ignore=tests/integration`

### Exit criteria фази

- ops cookie більше не похідний від `INTERNAL_API_TOKEN`;
- session server-side revocable;
- internal auth boundary стала явною і route-specific;
- немає fail-open поведінки при outage session store.

## Phase 3. Shared Admin Rate Limit

### Мета

Зробити rate limit для `/admin/auth/login` і `/admin/auth/2fa/verify` shared між усіма uvicorn workers і стійким до restart/process sharding.

### Цільовий результат фази

- ліміт більше не локальний до одного Python-процесу;
- login і 2FA мають чітко визначені buckets;
- outage rate-limit store не виглядає як "rate limit просто зник".

### Slice 3.1. Зафіксувати rate-limit модель

- Для login визначити bucket як мінімум по `client_ip`, і окремо оцінити bucket по normalized email.
- Для 2FA визначити bucket так, щоб brute-force по TOTP не обходився через зміну worker-процесу.
- Явно описати, що саме очищається після успішного login і після успішного 2FA.

### Slice 3.2. Перенести лічильники у shared store

- Замінити process-local [_FAILED_ATTEMPTS](/mnt/c/Users/User/Desktop/Quiz Arena/app/services/admin/rate_limit.py:7) на Redis-backed counters з TTL.
- Інкремент має бути atomic.
- Window expiry має керуватися TTL ключа, а не локальним `deque`.

### Slice 3.3. Визначити безпечну degraded semantics

- Якщо Redis для rate limiting недоступний, не повертатися мовчки до per-worker memory.
- Бажаний контракт для admin auth:
  - `503` для login / 2FA при недоступному rate-limit state store,
  - або інший явно задокументований fail-closed варіант.
- Structured logs повинні відрізняти:
  - `rate_limited`
  - `rate_limit_state_unavailable`

### Slice 3.4. Прибрати старий локальний fallback

- Або видалити старий in-memory store,
- або залишити його тільки для test doubles, але не для runtime.

### Тести в кінці фази

- Unit/route tests на:
  - накопичення failed attempts у shared store;
  - `429` після досягнення ліміту;
  - reset counters після успіху;
  - однакову поведінку для login і 2FA;
  - `503` або іншу обрану degraded semantics при outage store.
- Загальний backend gate:
  - `make lint && make format-check && make type-check`
  - `pytest -q --ignore=tests/integration`

### Exit criteria фази

- rate limit більше не per-worker;
- after-restart / multi-worker обходу старої моделі більше немає;
- degraded semantics явна і покрита тестами.

## Phase 4. Public Contact Anti-Abuse

### Мета

Знизити ризик spam/flood на публічний контактний flow без додавання великого продуктового редизайну.

### Цільовий результат фази

- масовий flood не проходить безконтрольно;
- боти відсікаються хоча б базовим honeypot + rate limit шаром;
- валідні student/partner flows не ламаються;
- рішення не тягне нову зовнішню залежність без окремого дозволу.

### Slice 4.1. Додати shared server-side rate limit для contact endpoints

- Поставити rate limit на [submit_contact](/mnt/c/Users/User/Desktop/Quiz Arena/app/api/routes/public_contact.py:127) для обох шляхів:
  - `/contact`
  - `/api/contact`
- Розрахунок bucket робити по client IP.
- Поріг зробити достатнім для нормального human use, але низьким для flood surface.

### Slice 4.2. Додати honeypot для обох публічних форм

- У frontend student/partner wizard додати приховане поле, яке люди не заповнюють.
- На backend:
  - якщо honeypot заповнено, не писати заявку в БД;
  - відповідь краще робити нейтральною (`202` / `{"ok": true}`), щоб не давати bot-oracle.

### Slice 4.3. Додати мінімальний abuse telemetry surface

- Логувати причину відсікання без PII-дампу:
  - `rate_limited`
  - `honeypot_triggered`
- За потреби додати окремий status/tag для auto-spam, якщо це не тягне міграцію або зайвий schema churn.
- Не розширювати цю фазу до CRM/notification feature work.

### Slice 4.4. Чітко відкласти зовнішній captcha-шар

- Не підключати captcha / anti-bot SaaS у першому проході.
- Якщо базовий shield виявиться недостатнім, це окрема follow-up задача, бо вона:
  - додає зовнішню залежність;
  - тягне нові env/config;
  - виходить за межі поточного мінімального remediation slice.

### Тести в кінці фази

- Backend tests на:
  - valid student payload accepted;
  - valid partner payload accepted;
  - honeypot-filled payload silently ignored;
  - rate limit спрацьовує після порогу;
  - flood path не пише необмежену кількість рядків у БД.
- Якщо змінюється frontend wizard:
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build`
  - `cd frontend && npm test` тільки якщо з'являється або змінюється frontend-covered logic.
- Загальний backend gate:
  - `make lint && make format-check && make type-check`
  - `pytest -q --ignore=tests/integration`

### Exit criteria фази

- contact endpoints мають базовий anti-abuse shield;
- honey/bot submissions не засмічують БД так само легко, як зараз;
- валідний public flow не регресує.

## Phase 5. Public Health Surface Reduction

### Мета

Прибрати витік operational internals назовні, не ламаючи внутрішні readiness/операційні перевірки.

### Цільовий результат фази

- зовнішній health contract більше не показує `database/redis/celery` breakdown;
- детальні health/readiness перевірки лишаються доступними для локального runtime, compose healthcheck або auth-protected surfaces;
- Caddy/public routing не світить зайвий operational state.

### Approval gate перед стартом фази

Ця фаза майже напевно зачіпає `deploy/Caddyfile`, а це protected path. Перед execution потрібне окреме підтвердження.

### Slice 5.1. Розділити public і internal health contracts

- Визначити новий контракт:
  - public endpoint: тільки coarse-grained `ok/degraded` або `live`;
  - detailed endpoint: тільки для внутрішнього runtime / auth-protected use.
- Не змішувати operational observability для адмініна з публічним anonymous health.

### Slice 5.2. Санітизувати backend health payload

- Переробити [health.py](/mnt/c/Users/User/Desktop/Quiz Arena/app/api/routes/health.py:1) так, щоб public surface не віддавав component-by-component payload.
- Якщо детальний payload лишається, винести його на окремий internal-only endpoint або лишити тільки для container-local checks.

### Slice 5.3. Змінити public routing

- У `deploy/Caddyfile` перестати публічно проксіювати legacy `/health` на detailed backend health.
- Варіанти закриття:
  - або `/health` віддає sanitized payload;
  - або `/health` взагалі прибирається з зовнішнього маршруту, а зовнішній uptime-check переходить на `/live`.
- Переконатися, що internal `docker compose` healthcheck продовжує працювати напряму по container-local endpoint.

### Slice 5.4. Оновити operational docs

- Оновити runbook/operations docs так, щоб:
  - public smoke checks використовували новий зовнішній endpoint;
  - detailed component checks залишалися лише у внутрішніх runbooks або admin-auth flow.
- Не змінювати historical archive docs без потреби.

### Тести в кінці фази

- Backend route tests на:
  - public health payload sanitized;
  - internal detailed checks still available only where expected.
- Prod-like smoke після зміни routing:
  - `curl` на public health endpoint;
  - `curl` на container-local readiness endpoint;
  - локальний compose smoke, якщо routing міняється через Caddy.
- Якщо правиться runbook, reread diff і звірка команд із фактичними endpoints.

### Exit criteria фази

- public health більше не розкриває стан `database/redis/celery`;
- compose/runtime healthchecks не зламані;
- документація відповідає новому контракту.

## Рекомендований PR slicing order

1. `security: exclude env files from docker build context`
2. `security: replace ops token-derived cookie with server-side session`
3. `security: move admin auth rate limit to shared store`
4. `security: add anti-abuse controls to public contact flow`
5. `security: reduce public health endpoint exposure`

## Definition of done для всього workstream

- Жоден із 5 findings не лишився в поточній формі.
- Для кожної фази є окремий доказовий test block.
- Не додано нових зовнішніх залежностей без окремого рішення.
- Не було прихованого scope drift у feature work або infra changes поза затвердженими межами.
