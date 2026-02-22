# Повний технічний аудит проєкту Quiz Arena

Дата аудиту: **2026-02-22**  
Локація аудиту: локальний workspace `/mnt/c/Users/User/Desktop/Quiz Arena`

## 1. Мета і рамки

Ціль: провести повний якісний аудит коду, інфраструктурних конфігів, тестового контуру та операційної готовності, з окремим висновком про готовність до навантаження **100000 користувачів**.

Що охоплено:
- backend-код (`app/`), задачі воркерів, API-роути, DB-репозиторії/моделі;
- CI/CD та deploy-конфіги (`.github/workflows`, `docker-compose*.yml`, `scripts/deploy.sh`);
- Alembic міграції та узгодженість зі схемою;
- тестовий контур (`tests/`), лінт/тайпчек/coverage;
- контентні та операційні артефакти (`QuizBank/`, `reports/`, `docs/`).

Що **не** виконувалось у цьому аудиті:
- реальний load/stress-тест (RPS/latency soak) на staging/production;
- pentest зовнішнього периметра та мережевої інфраструктури;
- економічна оцінка вартості інфраструктури для 100k.

## 2. Виконані перевірки (фактичні результати)

1. Статичний аналіз коду:
- `ruff check app tests` -> **All checks passed**.

2. Тайпчек:
- `mypy app tests` -> **FAILED**:
  - `tests/bot/helpers.py: error: Source file found twice under different module names: "helpers" and "tests.bot.helpers"`.

3. Тести (юнiт/бот/API/сервіси, без integration):
- `pytest -q --ignore=tests/integration` -> **223 passed**.

4. Інтеграційні тести на окремій test-БД:
- `pytest -q -s tests/integration` (із `DATABASE_URL=...quiz_arena_test`) -> **73 passed**.

5. Повний прогін з coverage (app):
- `pytest --cov=app --cov-report=term-missing -q` (із test-БД) -> **296 passed**, **TOTAL 84%**.

6. Security-аудит залежностей:
- `pip-audit` -> **No known vulnerabilities found** (пакет `quiz-arena-bot` не аудитується як локальний проєктний пакет, що очікувано).

7. Додаткова верифікація DX:
- `pytest -q` без test-`DATABASE_URL` -> **73 errors + 223 passed**, помилка захисту integration БД (очікуваний safe-guard, але важливо для DX-процесу).

## 3. Executive Summary

Проєкт у поточному стані:
- має сильну функціональну базу та високий рівень тестування (296 тестів проходять, coverage 84%);
- має ряд критичних і high-impact ризиків у reliability/scalability/операційному контурі;
- **не готовий** до впевненого продакшн-навантаження рівня **100000 користувачів** без цільового hardening.

Ключовий вердикт:
- **Функціональна готовність:** висока.
- **Операційна та масштабна готовність (100k):** недостатня.

## 4. Детальні знахідки

### P0 (Critical)

#### P0-1. Ризик втрати Telegram update при падінні воркера у статусі `PROCESSING`

Докази:
- слот обробки фіксується як `PROCESSING`: `app/workers/tasks/telegram_updates.py:19`, `app/workers/tasks/telegram_updates.py:25`, `app/workers/tasks/telegram_updates.py:41`;
- дублікати зі статусом `PROCESSING` відкидаються: `app/workers/tasks/telegram_updates.py:38`;
- retry-політика Celery для задачі не задана: `app/workers/tasks/telegram_updates.py:86`;
- стани зберігаються в `processed_updates`: `app/db/models/processed_updates.py:14`.

Проблема:
- якщо воркер аварійно завершується після встановлення `PROCESSING` і до `FAILED/PROCESSED`, повторна доставка того ж update може бути відхилена як duplicate.

Вплив:
- потенційна втрата апдейтів/дій користувачів у пікових або аварійних сценаріях.

Рекомендація:
- ввести reclaim-механізм `PROCESSING` зі TTL;
- додати `autoretry_for`, exponential backoff, max retries;
- додати метрику/алерт на застряглі `PROCESSING`.

#### P0-2. Прод-стек фактично не масштабується горизонтально (blocking для 100k)

Докази:
- фіксовані `container_name` для `api/worker/beat/caddy`: `docker-compose.prod.yml:39`, `docker-compose.prod.yml:73`, `docker-compose.prod.yml:102`, `docker-compose.prod.yml:120`;
- API стартує одним uvicorn-процесом без `--workers`: `docker-compose.prod.yml:53`.

Проблема:
- з `container_name` неможливо нормально масштабувати `docker compose --scale`;
- одиночний API-процес створює вузьке місце.

Вплив:
- відсутній шлях до еластичного масштабування для піків навантаження.

Рекомендація:
- прибрати `container_name` для масштабованих сервісів;
- перейти на multi-instance API + балансування;
- окремо планувати масштабування worker pool за чергами.

### P1 (High)

#### P1-1. Індексні прогалини для гарячих запитів БД

Докази:
- `purchases` активні фільтри по `status/paid_at/created_at`: `app/db/repo/purchases_repo.py:68`, `app/db/repo/purchases_repo.py:77`, `app/db/repo/purchases_repo.py:151`, `app/db/repo/purchases_repo.py:170`;  
  на моделі немає відповідних composite index: `app/db/models/purchases.py:32`;
- `referrals` часті фільтри/агрегації по `status/created_at/qualified_at/rewarded_at`: `app/db/repo/referrals_repo.py:67`, `app/db/repo/referrals_repo.py:93`, `app/db/repo/referrals_repo.py:148`, `app/db/repo/referrals_repo.py:214`, `app/db/repo/referrals_repo.py:225`;  
  індекси лише `referrer` і `code`: `app/db/models/referrals.py:21`;
- `outbox_events` фільтрація за `created_at` + `event_type`: `app/db/repo/outbox_events_repo.py:40`, `app/db/repo/outbox_events_repo.py:41`;  
  індексів немає (лише PK): `app/db/models/outbox_events.py:15`;
- offers-дашборд глобально рахує по `shown_at`: `app/db/repo/offers_repo.py:139`, `app/db/repo/offers_repo.py:146`, `app/db/repo/offers_repo.py:154`;  
  немає окремого/leading index по `shown_at`: `app/db/models/offers_impressions.py:16`.

Вплив:
- деградація latency і зростання CPU/IO на БД при рості даних.

Рекомендація (мінімум):
- `purchases(status, paid_at)` + partial для open invoices;
- `referrals(status, qualified_at)`, `referrals(created_at)`, `referrals(status, created_at)`;
- `outbox_events(event_type, created_at DESC)`, `outbox_events(status, created_at DESC)`;
- `offers_impressions(shown_at)`.

#### P1-2. Некоректність funnel-метрик офферів (CTR/conversion)

Докази:
- dismiss записує `clicked_at`: `app/db/repo/offers_repo.py:90`, `app/db/repo/offers_repo.py:92`;
- `clicks_total` рахується по `clicked_at is not null`: `app/db/repo/offers_repo.py:154`, `app/db/repo/offers_repo.py:156`;
- conversion ставиться на стадії `init_purchase`, до фактичної успішної оплати: `app/bot/handlers/payments.py:72`, `app/bot/handlers/payments.py:80`, `app/bot/handlers/payments.py:98`, `app/bot/handlers/payments.py:151`.

Вплив:
- завищений CTR;
- conversion інтерпретується як «ініціація покупки», а не «успішна оплата».

Рекомендація:
- розвести `clicked_at` і `dismissed_at`;
- для conversion вести окрему подію на `successful_payment`.

#### P1-3. `/ready` жорстко залежить від Celery + витік внутрішніх помилок в health payload

Докази:
- celery-check входить у readiness: `app/api/routes/health.py:73`, `app/api/routes/health.py:76`, `app/api/routes/health.py:103`;
- в health payload віддається `str(exc)`: `app/api/routes/health.py:35`, `app/api/routes/health.py:47`, `app/api/routes/health.py:65`;
- production healthcheck сервісу API б'є в `/ready`: `docker-compose.prod.yml:60`.

Вплив:
- worker-проблеми можуть валити readiness API;
- потенційний leakage внутрішніх деталей помилок.

Рекомендація:
- розділити `liveness` і `readiness` (API readiness без hard dependency на worker);
- санітизувати помилки в health-відповідях.

#### P1-4. Тайпчек зламаний, CI не ловить це

Докази:
- `mypy` падає на дубль-модулі `helpers/tests.bot.helpers`;
- у CI немає кроку `mypy`: `.github/workflows/ci.yml:57`, `.github/workflows/ci.yml:60`;
- `tests/bot` не є явним пакетом (`__init__.py` відсутній).

Вплив:
- регресії типізації можуть непомітно проходити через CI.

Рекомендація:
- виправити package layout для `tests`;
- додати `mypy` step у CI;
- зафіксувати `tool.mypy` конфіг у `pyproject.toml`.

#### P1-5. Конфіг доступу до internal/ops у production-шаблоні і runbook неузгоджений

Докази:
- `INTERNAL_API_ALLOWLIST`/`INTERNAL_API_TRUSTED_PROXIES` за замовчуванням localhost-only: `.env.production.example:10`, `.env.production.example:11`;
- у runbook обов'язкові змінні не включають ці поля: `docs/runbooks/first_deploy_and_rollback.md:26`.

Вплив:
- частий сценарій: після деплою internal/ops недоступні або працюють не так, як очікується (особливо за reverse-proxy).

Рекомендація:
- явний runbook-крок конфігурації allowlist/trusted proxies для прод.

### P2 (Medium)

#### P2-1. O(N)-патерн вибору питань у runtime банку

Докази:
- кожен підбір тягне списки id + сортування: `app/db/repo/quiz_questions_repo.py:24`, `app/db/repo/quiz_questions_repo.py:30`;
- fallback-проходи множать ці запити: `app/game/questions/runtime_bank.py:78`, `app/game/questions/runtime_bank.py:85`, `app/game/questions/runtime_bank.py:92`, `app/game/questions/runtime_bank.py:99`.

Вплив:
- зайве навантаження на БД/CPU під високою конкуренцією.

Рекомендація:
- кешувати candidate-id per mode/level;
- переходити до вибірки по cursor/rand-стратегії без витягування повного списку.

#### P2-2. Дублювання коду (maintainability)

Докази:
- дубль `_format_user_label` та `_build_question_text` в `start`/`gameplay`: `app/bot/handlers/start.py:37`, `app/bot/handlers/start.py:82`, `app/bot/handlers/gameplay.py:48`, `app/bot/handlers/gameplay.py:60`;
- дубль `_assert_internal_access` у 4 роутерах: `app/api/routes/internal_analytics.py:58`, `app/api/routes/internal_offers.py:59`, `app/api/routes/internal_promo.py:154`, `app/api/routes/internal_referrals.py:141`.

Вплив:
- підвищений ризик розсинхрону логіки доступу/форматування.

Рекомендація:
- винести спільні helper/auth-guard в shared модулі.

#### P2-3. Відсутня політика retention для технічних/аналітичних таблиць

Докази:
- таблиці з потенційно безперервним ростом: `processed_updates`, `outbox_events`, `analytics_events` (моделі: `app/db/models/processed_updates.py:11`, `app/db/models/outbox_events.py:12`, `app/db/models/analytics_events.py`);
- окремих cleanup/retention job для цих таблиць не знайдено у воркерах.

Вплив:
- зростання обсягу БД, погіршення продуктивності.

Рекомендація:
- retention jobs + архівація/партиціювання для event-потоків.

#### P2-4. Документація/репорти частково застарілі

Докази:
- `QuizBank/README.md` вказує 20 файлів і 5150 питань: `QuizBank/README.md:13`, `QuizBank/README.md:14`;  
  фактично у поточній папці 19 CSV і 5570 питань (перераховано скриптом аудиту);
- `reports/quizbank_ambiguity_scan.md` оперує старими назвами банків (напр. `Artikel_Sprint_Bank_A2_B1_210.csv`), яких вже немає: `reports/quizbank_ambiguity_scan.md:11`.

Вплив:
- ризик неправильних операційних рішень на базі старих даних.

Рекомендація:
- оновлювати inventory/ambiguity-репорти як частину CI/контент-пайплайну.

#### P2-5. Немає підтвердженого load/concurrency профілю

Докази:
- у milestone docs прямо зазначені missing stress/load перевірки: `docs/milestones/M8_tests.md:30`, `docs/milestones/M9_tests.md:38`, `docs/milestones/M4_ops.md:9`.

Вплив:
- невідомий реальний запас продуктивності під 100k.

Рекомендація:
- обов'язковий k6/Locust профіль із SLO-гейтами перед production scale-up.

### P3 (Low)

#### P3-1. Репродукованість dependency stack

Факт:
- використовується version-range без lockfile.

Вплив:
- дрейф dependency behavior між середовищами/датами.

Рекомендація:
- зафіксувати lockfile (pip-tools/uv/poetry equivalent) для CI/prod reproducibility.

## 5. Покриття тестами: що добре і що ризиково

Позитив:
- 296 тестів проходять;
- сильний інтеграційний контур на платежі, промо, реферали, internal дашборди;
- є safety-guard проти випадкового destructive integration run не на test-БД (`app/core/integration_db_safety.py`).

Ризикові зони за coverage:
- `app/economy/promo/service.py` (~41%);
- `app/bot/handlers/gameplay.py` (~45%);
- `app/api/routes/health.py` (~49%);
- `app/workers/tasks/referrals_observability.py` (~55%).

Висновок:
- coverage загалом хороший, але недостатній у частині критичних runtime-flow (gameplay/promo/ops health behavior).

## 6. Оцінка готовності до 100000 користувачів

### Поточний стан (якісна оцінка)
- Функціональна стабільність: **8/10**
- Надійність обробки подій: **5/10**
- Масштабованість інфраструктури: **4/10**
- Операційна керованість: **5/10**
- Безпека (app-рівень): **6/10**

Інтегрально: **~5.6/10**

### Вердикт
**Проєкт не готовий до цільового масштабу 100000 користувачів без обов'язкових доопрацювань P0/P1.**

Причина:
- немає надійної масштабної топології API/worker;
- є reliability gap у webhook processing;
- БД не оптимізована під частину гарячих аналітичних/операційних запитів;
- відсутні підтверджені stress/load результати.

## 7. Рекомендований roadmap

### Етап 0 (блокери запуску масштабування, 3-7 днів)
1. Закрити P0-1: retry + stale `PROCESSING` reclaim для Telegram updates.
2. Закрити P0-2: прибрати `container_name` для scale-сервісів, додати multi-worker API policy.
3. Закрити P1-2: виправити funnel-метрики (`dismiss != click`, conversion after successful payment).
4. Закрити P1-4: зелений `mypy` + додати у CI.

### Етап 1 (продуктивність і операційна готовність, 1-2 тижні)
1. Додати рекомендовані індекси і перевірити `EXPLAIN ANALYZE` для ключових запитів.
2. Розвести readiness/liveness, прибрати raw exception leakage.
3. Впровадити retention jobs для `processed_updates/outbox_events/analytics_events`.
4. Вирівняти production runbook для internal allowlist/trusted proxies.

### Етап 2 (підтвердження масштабу, 1-2 тижні)
1. Провести load/stress: API + Celery + Postgres (цільові профілі 10k concurrent, пікові burst).
2. Визначити SLO/SLI і ввести release gates (p95/p99 latency, queue lag, error rate).
3. Зафіксувати lockfile, оновити контент-репорти автоматично в pipeline.

## 8. Підсумковий висновок

Проєкт має хорошу функціональну зрілість і сильну тестову базу, але для **надійної** роботи на рівні **100000 користувачів** потрібні обов'язкові доробки в reliability, масштабуванні і DB-продуктивності.

Після закриття P0/P1 та проходження реального load/stress циклу можна переходити до контрольованого scale-up.
