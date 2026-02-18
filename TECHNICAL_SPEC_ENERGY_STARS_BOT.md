# TECHNICAL_SPEC_ENERGY_STARS_BOT

## 1) Executive Summary

Ми будуємо production-grade Telegram quiz-bot для німецької мови з монетизацією через Telegram Stars.

Цільова аудиторія:
- Free користувачі, які грають щодня короткими підходами.
- Активні користувачі, яким потрібен додатковий контент зараз.
- Premium користувачі, яким потрібні безліміт, турніри та розширена статистика.

Ключові механіки:
- `Energy`: контроль доступу до регулярної гри.
- `Micro`: імпульсні покупки `+10⚡`, `Mega Pack`, `Streak Saver`.
- `Premium`: Starter/Month/Season/Year з часовими entitlement.
- `Streak`: щоденна активність, freeze і auto-freeze.
- `Promo Codes`: безкоштовний Premium на термін або керована знижка на цільові продукти.

`РІШЕННЯ SPEC-00`: цей документ є фінальною технічною специфікацією для реалізації, тестування і виходу в прод для навантаження до 100,000 зареєстрованих користувачів.

---

## 2) Glossary / Терміни та визначення

### 2.1 Нормативні терміни

- `Питання` — атомарна одиниця контенту з 1 правильною відповіддю.
- `Вікторина` — 1 атомарний раунд = 1 питання + 1 відповідь користувача.
- `Гра` — безперервна взаємодія користувача в конкретному режимі, що складається з `N` вікторин.
- `Сесія (продуктова)` — денний free-пакет активності (20 вікторин/питань як база) на 1 локальну добу.
- `Сесія (runtime)` — технічний запис конкретного запуску гри в таблиці `quiz_sessions`.
- `Енергія` — ресурс допуску до атомарної вікторини.
- `Режим` — тип геймплею (Quick Mix, Artikel Sprint, Cases Practice тощо).
- `Locked` — режим недоступний без активного entitlement.
- `Premium` — часовий entitlement із безлімітною енергією і повним доступом до контенту.
- `Ledger` — незмінний бухгалтерський журнал усіх змін економіки (credit/debit).
- `Entitlement` — право доступу або бонус із чітким часом дії/лімітом використання.
- `Promo Code` — кодова сутність із правилами дії (grant/discount), лімітами та вікном валідності.
- `Promo Redemption` — факт застосування промокоду конкретним користувачем (ідемпотентний запис).
- `Discount Quote` — зафіксована ціна покупки після застосування промокоду, валідна обмежений час.

### 2.2 Фіналізація неоднозначностей

`РІШЕННЯ SPEC-TERM-01`: `1 енергія витрачається на 1 вікторину`, де вікторина = 1 питання.

`РІШЕННЯ SPEC-TERM-02`: продуктова `free-сесія` = `20 вікторин/20 питань` на локальну добу (Europe/Berlin) як гарантований безкоштовний пакет.

`РІШЕННЯ SPEC-TERM-02A`: `20/день` — гарантований безкоштовний базовий пакет на старті локальної доби; фактична кількість безкоштовних вікторин може бути більшою за рахунок `regen +1/30 хв` до cap `20` протягом доби.

`РІШЕННЯ SPEC-TERM-03`: технічна модель енергії двокошикова:
- `free_energy` (0..20, cap=20, regen +1/30 хв, щоденний top-up до 20 о 00:00 Berlin).
- `paid_energy` (>=0, без cap, не обнуляється щоденно).

`РІШЕННЯ SPEC-TERM-04`: для регулярної гри списання йде в такому порядку:
1. Premium активний -> списання 0.
2. `free_energy`.
3. `paid_energy`.
4. Якщо обидва кошики 0 -> блок гри.

`РІШЕННЯ SPEC-TERM-05`: фраза з базового документа `1 вікторина (5-7 питань)` нормалізується до атомарної моделі `1 вікторина = 1 питання` для однозначної реалізації `20 вікторин/20 питань`.

`РІШЕННЯ SPEC-TERM-06`: термін `session` у коді/БД (`quiz_sessions`) означає лише runtime-сесію і не означає денну free-сесію з бізнес-правил.

### 2.3 Приклади (мінімум 5)

1. Free user має `free_energy=20`, `paid_energy=0` -> може пройти 20 атомарних вікторин без покупки.
2. Free user має `free_energy=2`, `paid_energy=5`, Premium=off -> після 4 вікторин стане `free_energy=0`, `paid_energy=3`.
3. User купив `+10⚡` при `free_energy=0`, `paid_energy=0` -> `paid_energy=10`, доступно ще 10 вікторин.
4. User купив `Mega Pack` двічі поспіль -> `paid_energy +30`, а доступ 3 locked режимів подовжено сумарно до 48 годин.
5. User з активним Premium проходить 200 вікторин за день -> енергія не списується, ledger фіксує `energy_debit=0 (premium_bypass)`.
6. User зіграв о 23:59:50 Berlin -> активність зарахована в поточну добу streak.
7. User зіграв о 00:00:05 Berlin -> це вже нова доба для streak і daily challenge лімітів.

---

## 3) Non-Functional Requirements (NFR) для 100k користувачів

### 3.1 Продуктивність

- Зареєстровані користувачі: `100,000`.
- Цільовий DAU: `25,000-40,000`.
- Пікова конкурентність (одночасні активні): `6,000`.
- Вхідний піковий трафік webhook: `300 updates/sec`.
- Робочий steady-state: `70 updates/sec`.
- Ціль latency:
  - `p95` для webhook-обробки (до ACK) <= `800 ms`.
  - `p95` для start/play handler <= `1200 ms`.
  - `p99` для purchase credit транзакції <= `2000 ms`.

`РІШЕННЯ SPEC-NFR-01`: webhook ACK віддається швидко; важкі дії переносяться в worker/queue.

### 3.2 Надійність

- SLO доступності core-функцій (грати, купити, застосувати entitlement): `99.9%` на календарний місяць.
- RPO (допустима втрата даних): `<= 5 хв`.
- RTO (відновлення сервісу): `<= 30 хв`.
- Обробка Telegram updates: модель `at-least-once`, дублікати очікувані і безпечні.

`РІШЕННЯ SPEC-NFR-02`: усі критичні mutation-операції мають idempotency key + DB unique constraints.

### 3.3 Безпека

- Валідація `X-Telegram-Bot-Api-Secret-Token` для webhook.
- Захист від replay: таблиця `processed_updates` з унікальним `update_id`.
- Захист платежів: exactly-once credit через транзакції і ledger.
- Захист від фроду: velocity limits, referral anti-fraud scoring, anomaly detection.
- Захист promo-кодів: hash-зберігання коду + brute-force limits + denylist для зловживань.

### 3.4 Спостережуваність

- Структуровані JSON-логи з `request_id`, `user_id`, `update_id`, `purchase_id`.
- Метрики Prometheus:
  - `dau`, `wau`, `mau`, `conversion_free_to_micro`, `conversion_micro_to_premium`.
  - `purchase_success_rate`, `offer_ctr`, `energy_zero_events`, `streak_loss_rate`.
  - `queue_lag_seconds`, `webhook_error_rate`, `db_lock_wait_ms`.
- Distributed tracing: OpenTelemetry (webhook -> domain -> db -> worker).

### 3.5 Дані, резервні копії, міграції

- PostgreSQL: daily full backup + WAL archiving.
- Ретеншн бекапів: `35 днів`.
- Щотижневий restore drill на staging.
- Міграції тільки через Alembic, zero-downtime порядок:
  1. add nullable columns.
  2. backfill.
  3. switch code.
  4. add not null/constraints.

---

## 4) Product Requirements (повна логіка)

### 4.1 Energy System

#### 4.1.1 Константи

- `FREE_ENERGY_START = 20`
- `FREE_ENERGY_CAP = 20`
- `ENERGY_REGEN_INTERVAL_SEC = 1800` (30 хв)
- `ENERGY_COST_PER_QUIZ = 1`
- `DAILY_FREE_TOPUP_TIME = 00:00:00 Europe/Berlin`

`РІШЕННЯ SPEC-ENERGY-01`: `paid_energy` не має cap і не обнуляється при daily reset.

`РІШЕННЯ SPEC-ENERGY-02`: daily top-up працює як `free_energy = 20`, якщо на момент reset `free_energy < 20`.

#### 4.1.2 Regen логіка

Алгоритм (on-read/on-write):
1. `elapsed = now_utc - last_regen_at`.
2. `ticks = floor(elapsed / 1800 sec)`.
3. Якщо `ticks > 0` і Premium не активний:
   - `free_energy = min(20, free_energy + ticks)`.
   - `last_regen_at = last_regen_at + ticks*1800 sec`.
4. Якщо Premium активний, regen не обов'язковий для доступу, але поле `last_regen_at` оновлюється ліниво при завершенні Premium.

#### 4.1.3 Правила списання

- Перед стартом кожної атомарної вікторини виконується транзакційний `consume_energy(1)`.
- Якщо списання неуспішне -> вікторина не стартує.
- Daily Challenge, friend challenge (отриманий виклик), premium tournaments -> `energy_cost = 0`.

#### 4.1.4 Переповнення і top-up

- Regen не піднімає `free_energy` вище 20.
- Daily top-up не піднімає `free_energy` вище 20.
- Покупки енергії додають лише в `paid_energy`; переповнення немає.

#### 4.1.5 Edge cases

- Користувач натиснув `Play` з двох пристроїв одночасно: допускається тільки 1 успішне списання на 1 `idempotency_key` старту.
- Дубль Telegram callback: повторна обробка не списує енергію вдруге.
- Зміна часу на пристрої користувача: не впливає, бо серверний час UTC + timezone Europe/Berlin.
- Сервер перезапущено між списанням і стартом питання: atomic transaction гарантує або повне списання+створення attempt, або rollback.
- Premium закінчився під час активної вікторини: поточна вікторина завершується, наступна потребує стандартне списання.

#### 4.1.6 State machine (Energy)

**States**
- `E_PREMIUM_UNLIMITED`
- `E_AVAILABLE` (total_energy >= 4)
- `E_LOW` (total_energy in [1..3])
- `E_EMPTY` (total_energy = 0)

`total_energy = free_energy + paid_energy` коли Premium неактивний.

**Events**
- `EV_CONSUME_QUIZ`
- `EV_REGEN_TICK`
- `EV_DAILY_TOPUP`
- `EV_PURCHASE_ENERGY_CREDIT`
- `EV_PREMIUM_ON`
- `EV_PREMIUM_OFF`

**Transition table**

| From | Event | Condition | Action | To |
|---|---|---|---|---|
| E_AVAILABLE | EV_CONSUME_QUIZ | total_energy-1 >= 4 | debit 1 | E_AVAILABLE |
| E_AVAILABLE | EV_CONSUME_QUIZ | total_energy-1 in [1..3] | debit 1 | E_LOW |
| E_LOW | EV_CONSUME_QUIZ | total_energy-1 >= 1 | debit 1 | E_LOW |
| E_LOW | EV_CONSUME_QUIZ | total_energy-1 = 0 | debit 1 | E_EMPTY |
| E_EMPTY | EV_REGEN_TICK | free_energy increases to 1..3 | credit free | E_LOW |
| E_EMPTY | EV_PURCHASE_ENERGY_CREDIT | paid_energy += x | ledger credit | E_LOW/E_AVAILABLE |
| E_LOW | EV_REGEN_TICK | total_energy becomes >=4 | credit free | E_AVAILABLE |
| E_LOW/E_AVAILABLE/E_EMPTY | EV_DAILY_TOPUP | free_energy < 20 | set free_energy=20 | E_AVAILABLE |
| any non-premium | EV_PREMIUM_ON | premium entitlement active | no debit needed | E_PREMIUM_UNLIMITED |
| E_PREMIUM_UNLIMITED | EV_PREMIUM_OFF | total_energy=0 | recompute wallets | E_EMPTY |
| E_PREMIUM_UNLIMITED | EV_PREMIUM_OFF | total_energy in [1..3] | recompute wallets | E_LOW |
| E_PREMIUM_UNLIMITED | EV_PREMIUM_OFF | total_energy>=4 | recompute wallets | E_AVAILABLE |

---

### 4.2 Free Tier

#### 4.2.1 Доступно безкоштовно

- `20` free energy як денний базовий пакет.
- `+1` free energy кожні `30 хв` до cap `20`.
- Доступні режими:
  - Quick Mix A1-A2
  - Artikel Sprint
  - Daily Challenge (1 раз/день, 0 енергії)
- Streak система.
- Реферальна система.
- Challenge друзям (отриманий виклик — 0 енергії).

#### 4.2.2 Заблоковано у Free

- 12 додаткових режимів.
- Endless Mode.
- Logik Lücke.
- Grammar Boss.
- Premium tournaments.
- Pro статистика.

#### 4.2.3 UX при `energy=0` (німецькою)

- `msg.energy.empty.title`: `Deine Energie ist leer.`
- `msg.energy.empty.body`: `Du brauchst 1⚡ pro Quiz. Warte auf Aufladung oder hol dir ein Paket.`
- Кнопки:
  - `btn.wait`: `Warten`
  - `btn.buy.energy10`: `⚡ +10 Energie (10⭐)`
  - `btn.buy.megapack`: `📦 Mega Pack (15⭐)`
  - `btn.buy.premium`: `💎 Premium`
  - `btn.daily.challenge`: `🎯 Daily Challenge`

#### 4.2.4 Edge cases

- User має `energy=0`, але Daily Challenge ще не зіграний сьогодні -> Daily Challenge доступний.
- User має `energy=0`, отримав friend challenge -> вхід дозволений без списання.
- User клікає locked режим при free -> показується upsell, гра не стартує.
- User повернувся після 5 днів: перед меню виконуються daily reset, regen і offer evaluation в одному пайплайні.

---

### 4.3 Micro-transactions

#### 4.3.1 Каталог продуктів

1. `ENERGY_10`
- Ціна: `10⭐`
- Ефект: `paid_energy +10`
- Entitlement: немає

2. `MEGA_PACK_15`
- Ціна: `15⭐`
- Ефект: `paid_energy +15`
- Entitlement: `mode_access` для 3 режимів на `24h`
  - Cases Practice
  - Trennbare Verben
  - Word Order

3. `STREAK_SAVER_20`
- Ціна: `20⭐`
- Ефект: `streak_saver_token +1`
- Обмеження: `max 1 purchase / 7 днів` (ковзне вікно)

#### 4.3.2 Тригери показу

- `energy=0` -> пропозиція `ENERGY_10` + `MEGA_PACK_15`.
- `energy in [1..3]` -> м'який банер `ENERGY_10`.
- `друга покупка ENERGY_10 за 7 днів` -> upsell `MEGA_PACK_15`.
- `клік по locked режиму` -> upsell `MEGA_PACK_15`.
- `streak > 7` -> upsell `MEGA_PACK_15`.
- `streak > 14` і час >= 22:00 Berlin без активності дня -> upsell `STREAK_SAVER_20`.

#### 4.3.3 Правила застосування (ledger + idempotency)

- Кожна покупка має `purchase_id (UUID)` + `idempotency_key`.
- Кредитування виконується рівно 1 раз:
  - unique `telegram_payment_charge_id`.
  - unique `purchases.idempotency_key`.
  - unique `ledger_entries.idempotency_key`.
- Ефект покупки застосовується в одній DB транзакції:
  1. lock purchase row `FOR UPDATE`.
  2. перевірка статусу (`PAID_UNCREDITED`).
  3. write ledger credits.
  4. update wallets/entitlements.
  5. статус `CREDITED`.

#### 4.3.4 State machine (Purchase -> Credit -> Entitlement)

**States**
- `P_CREATED`
- `P_INVOICE_SENT`
- `P_PRECHECKOUT_OK`
- `P_PAID_UNCREDITED`
- `P_CREDITED`
- `P_CREDIT_REVIEW`
- `P_FAILED`
- `P_REFUNDED`

**Events**
- `EV_INIT_PURCHASE`
- `EV_INVOICE_SENT`
- `EV_PRECHECKOUT_APPROVED`
- `EV_SUCCESSFUL_PAYMENT`
- `EV_APPLY_CREDIT`
- `EV_APPLY_CREDIT_DUPLICATE`
- `EV_CREDIT_RETRIES_EXHAUSTED`
- `EV_PAYMENT_FAIL`
- `EV_REFUND`

**Transition table**

| From | Event | Condition | Action | To |
|---|---|---|---|---|
| P_CREATED | EV_INVOICE_SENT | invoice accepted | persist invoice meta | P_INVOICE_SENT |
| P_INVOICE_SENT | EV_PRECHECKOUT_APPROVED | pre-checkout ok | save query id | P_PRECHECKOUT_OK |
| P_PRECHECKOUT_OK | EV_SUCCESSFUL_PAYMENT | successful_payment received | save charge ids | P_PAID_UNCREDITED |
| P_PAID_UNCREDITED | EV_APPLY_CREDIT | not credited yet | ledger + entitlement | P_CREDITED |
| P_PAID_UNCREDITED/P_CREDITED | EV_APPLY_CREDIT_DUPLICATE | duplicate webhook | no-op | unchanged |
| P_PAID_UNCREDITED | EV_CREDIT_RETRIES_EXHAUSTED | retries exhausted | mark for manual review | P_CREDIT_REVIEW |
| P_CREDIT_REVIEW | EV_APPLY_CREDIT | manual replay succeeded | ledger + entitlement | P_CREDITED |
| P_CREATED/P_INVOICE_SENT/P_PRECHECKOUT_OK | EV_PAYMENT_FAIL | timeout/reject | mark failed | P_FAILED |
| P_CREDITED | EV_REFUND | refund approved | compensating ledger debit | P_REFUNDED |

#### 4.3.5 Німецькі тексти purchase flow

- `msg.purchase.energy10.offer`: `Sofort weiterspielen? Hol dir +10 Energie für 10⭐.`
- `msg.purchase.megapack.offer`: `Mehr Wert: +15⚡ und 3 Modi für 24 Stunden für 15⭐.`
- `msg.purchase.streaksaver.offer`: `Deine Serie ist wichtig. Sichere einen Tag mit Streak Saver für 20⭐.`
- `msg.purchase.success.energy10`: `Erfolg! +10 Energie wurde gutgeschrieben.`
- `msg.purchase.success.megapack`: `Mega Pack aktiv: +15 Energie und 3 Modi sind jetzt freigeschaltet.`
- `msg.purchase.success.streaksaver`: `Streak Saver ist bereit. Ein Fehltag wird automatisch geschützt.`

#### 4.3.6 Edge cases

- Повтор `successful_payment` update 3 рази -> credit виконується 1 раз, 2 рази no-op.
- User купив `STREAK_SAVER_20` вдруге в межах 7 днів -> покупка блокується до інвойсу.
- User купив `MEGA_PACK_15` під активним Premium -> `paid_energy +15` обов'язково, 24h mode_access записується і починає діяти від `max(now, existing_end)`.
- Сервер впав після статусу `PAID_UNCREDITED` -> recovery job доганяє і доводить до `P_CREDITED`.

---

### 4.4 Premium Subscriptions

#### 4.4.1 Плани і ціни

- `PREMIUM_STARTER`: `29⭐` / `7 днів`
- `PREMIUM_MONTH`: `99⭐` / `30 днів`
- `PREMIUM_SEASON`: `249⭐` / `90 днів`
- `PREMIUM_YEAR`: `499⭐` / `365 днів`

#### 4.4.2 Що відкриває Premium

- Безлімітна енергія (`energy bypass`).
- Всі режими.
- Турніри Premium.
- Pro статистика.
- Badges згідно плану.

#### 4.4.3 Auto-freeze правила

- Starter: `0` auto-freeze/тиждень.
- Month: `1` auto-freeze/тиждень.
- Season: `безліміт` auto-freeze.
- Year: `безліміт` auto-freeze.

#### 4.4.4 Завершення Premium

При `premium_expired`:
- доступ до всіх режимів через Premium припиняється.
- активні Mega Pack mode_access залишаються до своїх `ends_at`.
- енергія повертається до стандартної моделі (`free + paid`).
- streak auto-freeze більше не застосовується.

#### 4.4.5 Upgrade/Downgrade

`РІШЕННЯ SPEC-PREM-01`: усі Premium плани реалізуються як fixed-term entitlement (без auto-renew), щоб єдино підтримати 7/30/90/365.

`РІШЕННЯ SPEC-PREM-02`: ієрархія планів: `Starter < Month < Season < Year`.

`РІШЕННЯ SPEC-PREM-03`:
- Якщо куплено вищий план під час активного Premium:
  - новий tier активується негайно;
  - `premium_ends_at = existing_premium_ends_at + new_plan_duration`.
- Якщо куплено нижчий/той самий plan під час активного вищого -> покупка блокується, показується renew після завершення.

#### 4.4.6 Німецькі тексти UI

- `msg.premium.starter`: `Premium Starter: 7 Tage ohne Limits für 29⭐.`
- `msg.premium.month`: `Premium Month: 30 Tage, bester Wert, nur 99⭐.`
- `msg.premium.season`: `Premium Season: 90 Tage für 249⭐.`
- `msg.premium.year`: `Premium Year: 365 Tage für 499⭐.`
- `msg.premium.expired`: `Dein Premium ist abgelaufen. Du bist wieder im Free-Modus.`
- `msg.premium.upgrade.success`: `Upgrade aktiv. Deine Premium-Zeit wurde verlängert.`

#### 4.4.7 Edge cases

- Premium закінчився в момент активної відповіді: поточна відповідь зараховується, наступний старт — за звичайними правилами.
- Premium + Mega Pack перетин: подвійного відкриття режимів не виникає, mode_access не втрачається.
- User на Season купує Year: tier -> Year одразу, duration додається до існуючого кінця.
- User на Year пробує купити Starter: блокувати з кодом `E_PREMIUM_DOWNGRADE_NOT_ALLOWED`.

---

### 4.5 Streak System

#### 4.5.1 Що рахується активністю дня

День зарахований як активний, якщо виконано хоча б одну умову:
- Завершено >=1 атомарну вікторину у будь-якому режимі з `counts_for_streak=true`.
- Завершено Daily Challenge.

`РІШЕННЯ SPEC-STREAK-01`: відкриття меню без гри streak не підтримує.

#### 4.5.2 Daily reset

- Таймзона: `Europe/Berlin`.
- Границя дня: `00:00:00` локального часу Berlin.

#### 4.5.3 Правила зміни streak

- Якщо є активність у день `D` і в день `D-1` streak був збережений (play/freeze), то `current_streak += 1`.
- Якщо активність у день `D`, але в `D-1` streak було втрачено, `current_streak = 1`.
- Якщо день пропущено:
  - За наявності `streak_saver_token` або доступного `premium_auto_freeze` -> день позначається frozen, streak не падає.
  - Інакше `current_streak = 0`.

#### 4.5.4 Streak Saver

- Токен купується окремо (`20⭐`).
- Автозастосування: при rollover дня, якщо немає активності і токен доступний.
- Ліміт купівлі: 1 раз на 7 днів (ковзне вікно).

#### 4.5.5 Premium auto-freeze

- Month: максимум 1 автозаморозка на календарний тиждень (Berlin week, Monday 00:00 -> Sunday 23:59:59).
- Season/Year: без тижневого ліміту.

#### 4.5.6 State machine (Streak)

**States**
- `S_NO_STREAK`
- `S_ACTIVE_TODAY`
- `S_AT_RISK` (новий день почався, активності ще немає)
- `S_FROZEN_TODAY`

**Events**
- `EV_DAY_START`
- `EV_ACTIVITY_DONE`
- `EV_DAY_END_NO_ACTIVITY`
- `EV_APPLY_SAVER`
- `EV_APPLY_AUTO_FREEZE`

**Transition table**

| From | Event | Condition | Action | To |
|---|---|---|---|---|
| S_NO_STREAK | EV_ACTIVITY_DONE | first activity today | current_streak=1 | S_ACTIVE_TODAY |
| S_ACTIVE_TODAY | EV_DAY_START | new local day | mark at risk | S_AT_RISK |
| S_AT_RISK | EV_ACTIVITY_DONE | played today | current_streak +=1 | S_ACTIVE_TODAY |
| S_AT_RISK | EV_DAY_END_NO_ACTIVITY | saver token available | consume token, keep streak | S_FROZEN_TODAY |
| S_AT_RISK | EV_DAY_END_NO_ACTIVITY | premium freeze available | consume premium freeze, keep streak | S_FROZEN_TODAY |
| S_AT_RISK | EV_DAY_END_NO_ACTIVITY | no freeze | current_streak=0 | S_NO_STREAK |
| S_FROZEN_TODAY | EV_DAY_START | next day | at risk again | S_AT_RISK |

#### 4.5.7 Edge cases

- Гра о `23:59:59` Berlin -> це поточна доба.
- Гра о `00:00:00` Berlin -> це нова доба.
- DST spring forward (23-годинний день) -> streak межа все одно о локальній 00:00.
- DST fall back (25-годинний день) -> подвійна година не створює дубль-дня; ключем є локальна дата.
- Два паралельні завершення вікторини в одну секунду -> у streak рахується 1 активність дня без дублю.

---

### 4.6 Режим “Locked/Unlocked” та 24h доступ

#### 4.6.1 Entitlement model

Доступ до режиму визначається в такому порядку:
1. Активний Premium -> доступ до всіх режимів.
2. Активний mode entitlement (наприклад, Mega Pack mode_access).
3. Free base доступ.
4. Інакше `locked`.

#### 4.6.2 Правило 24h

- Старт 24h: точний `credited_at` покупки `MEGA_PACK_15` (UTC timestamp).
- Кінець 24h: `credited_at + 86400 sec`.
- Відображення в UI в локальному Berlin часі.

#### 4.6.3 Premium + Mega одночасно

- Premium не відміняє ефект Mega Pack на `paid_energy +15`.
- Mode-access entitlement від Mega все одно записується.
- Якщо Premium закінчиться раніше за `mega_mode_access_end`, режими залишаться доступними до кінця Mega.

#### 4.6.4 Mega Pack куплено двічі

`РІШЕННЯ SPEC-LOCK-01`: для кожного з 3 режимів `ends_at = max(current_ends_at, now) + 24h`.

#### 4.6.5 State machine (Entitlement)

**States**
- `T_SCHEDULED`
- `T_ACTIVE`
- `T_EXPIRED`
- `T_CONSUMED`
- `T_REVOKED`

**Events**
- `EV_GRANT`
- `EV_ACTIVATE_NOW`
- `EV_TIME_EXPIRE`
- `EV_CONSUME`
- `EV_REFUND_REVOKE`

**Transition table**

| From | Event | Condition | Action | To |
|---|---|---|---|---|
| (none) | EV_GRANT | starts_at > now | create record | T_SCHEDULED |
| (none)/T_SCHEDULED | EV_ACTIVATE_NOW | starts_at <= now < ends_at | set active | T_ACTIVE |
| T_ACTIVE | EV_TIME_EXPIRE | now >= ends_at | mark expired | T_EXPIRED |
| T_ACTIVE | EV_CONSUME | one-time token used | mark consumed | T_CONSUMED |
| T_ACTIVE/T_SCHEDULED | EV_REFUND_REVOKE | refund approved | revoke access | T_REVOKED |

#### 4.6.6 Edge cases

- Користувач в середині сесії втратив entitlement (end_at настав) -> поточне питання завершується, наступне блокується.
- `ends_at` припало на DST shift -> порівняння тільки в UTC.
- Повторне grant з тим самим idempotency key -> no-op.

---

### 4.7 Offers & Triggers (Upsell funnel)

#### 4.7.1 Trigger matrix

| Trigger code | Умова | Offer | Priority |
|---|---|---|---|
| TRG_ENERGY_ZERO | total_energy=0, premium=off | ENERGY_10 + MEGA_PACK + PREMIUM | 100 |
| TRG_ENERGY_LOW | total_energy in [1..3], premium=off | ENERGY_10 banner | 60 |
| TRG_ENERGY10_SECOND_BUY | 2 покупки ENERGY_10 за 7 днів | MEGA_PACK | 80 |
| TRG_LOCKED_MODE_CLICK | click locked mode, premium=off | MEGA_PACK | 90 |
| TRG_STREAK_GT7 | streak>7 | MEGA_PACK | 50 |
| TRG_STREAK_RISK_22 | streak>14, local time>=22:00, no activity today | STREAK_SAVER | 95 |
| TRG_STREAK_MILESTONE_30 | streak>=30 | STREAK_SAVER + PREMIUM_MONTH | 55 |
| TRG_COMEBACK_3D | no activity >=3 дні | COMEBACK (free + discount) | 85 |
| TRG_MEGA_THIRD_BUY | 3 покупки MEGA за 14 днів | PREMIUM_STARTER | 88 |
| TRG_STARTER_EXPIRED | starter expired <=48h | PREMIUM_MONTH | 92 |
| TRG_MONTH_EXPIRING | month expires <=72h | SEASON/YEAR | 70 |
| TRG_WEEKEND_FLASH | Friday 18:00 - Sunday 23:59 Berlin | FLASH_OFFER | 40 |

#### 4.7.2 Частота показів (anti-spam)

- Максимум 1 blocking modal / `6 год`.
- Максимум 3 monetization impressions / добу.
- Один і той самий `offer_code` не частіше ніж 1 раз / `24 год`.
- Push-нотифікації: максимум 2/добу.
- Якщо користувач натиснув `Nicht zeigen` для offer -> mute цього offer на `72 год`.

#### 4.7.3 Пріоритети при конфлікті

1. `TRG_ENERGY_ZERO`
2. `TRG_STREAK_RISK_22`
3. `TRG_LOCKED_MODE_CLICK`
4. `TRG_STARTER_EXPIRED`
5. `TRG_COMEBACK_3D`
6. `TRG_ENERGY10_SECOND_BUY`
7. `TRG_MEGA_THIRD_BUY`
8. `TRG_MONTH_EXPIRING`
9. `TRG_ENERGY_LOW`
10. `TRG_STREAK_GT7`
11. `TRG_STREAK_MILESTONE_30`
12. `TRG_WEEKEND_FLASH`

#### 4.7.4 Німецькі UI тексти

- `msg.offer.energy.low`: `Nur noch wenig Energie. +10⚡ für 10⭐?`
- `msg.offer.energy.zero`: `Du bist leer. Spiele jetzt weiter mit +10⚡ oder Mega Pack.`
- `msg.offer.mega.after_second_energy`: `Du kaufst oft +10⚡. Mega Pack gibt dir mehr für weniger.`
- `msg.offer.locked.mode`: `Dieser Modus ist gesperrt. Mega Pack schaltet ihn 24 Stunden frei.`
- `msg.offer.streak.risk`: `Deine Serie ist in Gefahr. Spiele jetzt oder sichere sie mit Streak Saver.`
- `msg.offer.comeback`: `Willkommen zurück. Heute: +20 Energie geschenkt und Mega Pack Rabatt.`
- `msg.offer.starter.to.month`: `Dein Starter ist vorbei. Mit Month bleibst du ohne Limits.`
- `msg.offer.month.to.season_year`: `Du spielst konstant. Season und Year sparen dir Sterne.`

#### 4.7.5 Edge cases

- Одночасно спрацювали `energy=0` і `locked mode click` -> показується тільки higher priority `energy=0`.
- Push відкладений, але user вже купив Premium -> перед відправкою робити ре-evaluate умов.
- `offer_impression` запис не створився через тимчасову помилку -> показ блокується до успішного логування (щоб не ламати anti-spam).

---

### 4.8 Referral / Viral

#### 4.8.1 Правила запрошень

- Кожен user має стабільний `referral_code`.
- Реферальний лінк: `https://t.me/<bot_username>?start=ref_<code>`.
- Один новий user може бути прив'язаний лише до 1 referrer.

#### 4.8.2 Умова "кваліфікованого" реферала

Referral вважається кваліфікованим, якщо invited user:
1. Зареєстрований по рефкоду.
2. Завершив мінімум `20` атомарних вікторин за `14 днів`.
3. Має активність мінімум у `2 різні локальні дні`.

#### 4.8.3 Винагороди

`РІШЕННЯ SPEC-REF-01`: за кожні `3` кваліфіковані реферали referrer отримує вибір:
- `MEGA_PACK_15` (безкоштовно), або
- `PREMIUM_STARTER` на 7 днів.

`РІШЕННЯ SPEC-REF-02`: максимум `2` реферальні нагороди на календарний місяць.

`РІШЕННЯ SPEC-REF-03`: після досягнення milestone слот винагороди переходить у `awaiting choice` (derived runtime state, без окремого DB status) і видається тільки після явного вибору користувача через callback `referral:reward:<reward_code>`.

#### 4.8.4 Anti-fraud

- Заборонено self-ref: `referrer_user_id != referred_user_id`.
- Заборонено циклічні пари (`A->B` і `B->A`) у межах 30 днів.
- Velocity rule: >10 нових referral starts/добу для одного referrer -> ручна/автоматична перевірка.
- Reward delay: слот винагороди стає доступним для claim не раніше ніж через `48 год` після досягнення умов; за цей час виконується risk check.
- Підозрілі ланцюжки позначаються `status=REJECTED_FRAUD`, без видачі нагороди.

#### 4.8.5 Edge cases

- Invited user видалив акаунт до кваліфікації -> referral event закривається як `CANCELED`.
- Дубль `/start ref_code` після реєстрації -> referrer не змінюється.
- User досяг 3 рефералів, але вже ліміт 2 нагород/місяць -> reward не видається в поточному місяці; записується як `DEFERRED_LIMIT`, повторна перевірка виконується о 00:05 першого дня наступного місяця (Berlin).

---

### 4.9 Promo Codes

#### 4.9.1 Scope і типи

`РІШЕННЯ SPEC-PROMO-01`: у v1 підтримуються 2 типи промокодів:
- `PROMO_PREMIUM_GRANT`: безкоштовний Premium на `7/30/90` днів.
- `PROMO_PERCENT_DISCOUNT`: відсоткова знижка на цільовий продукт (`Premium` або конкретний micro product).

`РІШЕННЯ SPEC-PROMO-02`: промокод у v1 одноразовий на користувача (`max_uses_per_user = 1`).

`РІШЕННЯ SPEC-PROMO-03`: discount застосовується лише в `purchase/init`; ціна фіксується в purchase і далі не перераховується.

`РІШЕННЯ SPEC-PROMO-04`: формула знижки:
- `discounted = ceil(base_price * (100 - discount_percent) / 100)`
- `final_price = max(1, discounted)`
- приклад: `99⭐` при `-50%` -> `50⭐`; `29⭐` при `-50%` -> `15⭐`.

#### 4.9.2 Бізнес-правила

- Промокод нормалізується: trim, uppercase, видалення пробілів і дефісів.
- Код валідний, якщо:
  - статус кампанії `ACTIVE`;
  - `valid_from <= now_utc < valid_until`;
  - не вичерпано `max_total_uses`;
  - користувач ще не використав цей код;
  - виконані умови сегмента (`new_users_only`, `first_purchase_only`, `target_scope`).
- Для `PROMO_PREMIUM_GRANT` entitlement видається одразу при redeem.
- Для `PROMO_PERCENT_DISCOUNT` створюється `discount quote` з TTL `15 хв`; при оплаті quote стає `CONSUMED`.

#### 4.9.3 Флоу застосування

Flow A (безкоштовний Premium):
1. User вводить код.
2. Backend валідує код і anti-abuse ліміти.
3. Створює `promo_redemption` зі статусом `APPLIED`.
4. Створює Premium entitlement на 7/30/90 днів.
5. Пише ledger entry `PROMO_GRANT`.

Flow B (знижка):
1. User вводить код.
2. Backend створює `promo_redemption` зі статусом `RESERVED` (`reserved_until=now+15m`).
3. User запускає `purchase/init` з `promo_redemption_id`.
4. Backend фіксує `base_stars_amount`, `discount_stars_amount`, `stars_amount`.
5. Після `successful_payment` redemption -> `APPLIED`; при timeout -> `EXPIRED`.

#### 4.9.4 State machine (Promo Redemption)

**States**
- `PR_CREATED`
- `PR_VALIDATED`
- `PR_RESERVED`
- `PR_APPLIED`
- `PR_EXPIRED`
- `PR_REJECTED`
- `PR_REVOKED`

**Events**
- `EV_REDEEM_REQUEST`
- `EV_VALIDATE_OK`
- `EV_RESERVE_DISCOUNT`
- `EV_APPLY_GRANT`
- `EV_APPLY_ON_PURCHASE_CREDIT`
- `EV_RESERVATION_TIMEOUT`
- `EV_REJECT`
- `EV_REFUND_REVOKE`

**Transition table**

| From | Event | Condition | Action | To |
|---|---|---|---|---|
| PR_CREATED | EV_VALIDATE_OK | code valid | persist validation snapshot | PR_VALIDATED |
| PR_VALIDATED | EV_APPLY_GRANT | promo_type=PREMIUM_GRANT | grant entitlement + ledger | PR_APPLIED |
| PR_VALIDATED | EV_RESERVE_DISCOUNT | promo_type=PERCENT_DISCOUNT | set reserved_until | PR_RESERVED |
| PR_RESERVED | EV_APPLY_ON_PURCHASE_CREDIT | linked purchase credited | mark consumed | PR_APPLIED |
| PR_RESERVED | EV_RESERVATION_TIMEOUT | now>=reserved_until | release reservation | PR_EXPIRED |
| PR_CREATED/PR_VALIDATED | EV_REJECT | invalid/rate-limited/not-applicable | store reject_reason | PR_REJECTED |
| PR_APPLIED | EV_REFUND_REVOKE | refunded purchase or promo rollback | revoke grant/discount effect | PR_REVOKED |

#### 4.9.5 Німецькі UI тексти

- `msg.promo.input.hint`: `Gib deinen Promo-Code ein.`
- `msg.promo.success.grant`: `Promo-Code aktiviert. Premium wurde freigeschaltet.`
- `msg.promo.success.discount`: `Promo-Code akzeptiert. Dein Rabatt ist 15 Minuten reserviert.`
- `msg.promo.error.invalid`: `Dieser Promo-Code ist ungültig.`
- `msg.promo.error.expired`: `Dieser Promo-Code ist abgelaufen.`
- `msg.promo.error.used`: `Du hast diesen Promo-Code bereits verwendet.`
- `msg.promo.error.not_applicable`: `Dieser Promo-Code passt nicht zu diesem Produkt.`
- `msg.promo.error.rate_limited`: `Zu viele Versuche. Bitte versuche es später erneut.`

#### 4.9.6 Edge cases

- Паралельний redeem одного коду з двох девайсів -> успішний рівно один `promo_redemption` через `UNIQUE(code_id, user_id)` і row lock.
- Discount code зарезервовано, але purchase не завершено -> після 15 хв `PR_EXPIRED`; у v1 повторне використання цього коду тим самим користувачем заборонене.
- User ввів discount code для нецільового продукту -> `PR_REJECTED` з `reject_reason=NOT_APPLICABLE`, без створення purchase.
- Promo grant на активний Premium -> `premium_ends_at = max(current_ends_at, now) + grant_days`.
- Refund покупки, зробленої зі знижкою -> компенсуючий ledger debit на фактично списану суму (`stars_amount`), а `promo_redemption` -> `PR_REVOKED`.

---

## 5) System Architecture (production)

### 5.1 Компоненти

1. `Webhook API` (FastAPI)
- приймає Telegram updates.
- валідує secret token.
- dedup update_id.
- маршрутизує у domain handlers.

2. `Bot Application Layer`
- команди/кнопки.
- локалізовані тексти (de).
- без бізнес-логіки.

3. `Domain Services`
- energy service.
- streak service.
- purchase service.
- entitlement service.
- offers service.
- promo service (validation, redemption, discount quote).

4. `Payments Listener`
- pre_checkout_query handler.
- successful_payment handler.
- refund/reconciliation service.

5. `Worker` (Celery)
- async jobs: offers push, reconciliation, expiry sweeps, analytics aggregation.

6. `Scheduler` (Celery Beat)
- регулярні задачі часу.

7. `PostgreSQL`
- source of truth.

8. `Redis`
- queue broker, rate limiting, short-lived locks, cache.

9. `Analytics`
- події у `events` + агрегатор в `analytics_daily`.

### 5.2 Черги і фонова обробка

- Queue `q_high`: платежі, entitlement expiry, streak rollover jobs.
- Queue `q_normal`: offers, reminders, referral checks, promo review jobs.
- Queue `q_low`: аналітичні підрахунки, архівація.

`РІШЕННЯ SPEC-ARCH-01`: критичні гроші/енергія обробляються синхронно в транзакції, а не eventual async.

### 5.3 Кешування

- `user_access_cache:{user_id}` TTL `30 sec`.
- `offer_cooldown_cache:{user_id}` TTL `5 min`.
- Кеш ніколи не є джерелом істини для списань або credit.

### 5.4 Rate limiting

- Inbound per user: `5 req/sec`, burst `10`.
- Callback spam guard: `1 interactive action / 300 ms`.
- Outbound Telegram:
  - global token bucket `28 msg/sec`.
  - per-chat `1 msg/sec`.
  - retry with jitter backoff on `429`.

### 5.5 Deployment (один регіон, горизонтальне масштабування)

- Регіон: `eu-central`.
- Stateless app pods:
  - `bot-api`: 3 replicas.
  - `worker`: 3 replicas.
  - `scheduler`: 1 replica (leader lock).
- PostgreSQL: primary + standby replica.
- Redis: primary + persistence enabled.
- Ingress TLS termination.

### 5.6 Edge cases

- Scheduler стартував у двох інстансах -> leader lock через Redis key з renewal.
- Redis недоступний -> degradate: rate limit у memory, критичні транзакції продовжують через DB.
- Telegram outage -> webhook queue накопичується, після відновлення обробка idempotent.

---

## 6) Data Model (PostgreSQL) — обов’язково

### 6.1 Загальні принципи

- Усі timestamps: `timestamptz` в UTC.
- Локальна дата Berlin зберігається окремими полями `*_local_date` де потрібно.
- Критичні таблиці мають `created_at`, `updated_at`, `version` (optimistic lock).
- DDL порядок для взаємних FK (`purchases` <-> `promo_redemptions`) виконується у 2 кроки: create tables -> add fk constraints через `ALTER TABLE`.

### 6.2 Таблиця `users`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| id | bigint PK | no | PK |
| telegram_user_id | bigint | no | UNIQUE |
| username | text | yes | idx_users_username |
| first_name | text | yes | - |
| language_code | varchar(8) | no | default 'de' |
| timezone | varchar(64) | no | default 'Europe/Berlin' |
| referral_code | varchar(16) | no | UNIQUE |
| referred_by_user_id | bigint FK users(id) | yes | idx_users_referred_by |
| status | varchar(16) | no | check in ('ACTIVE','BLOCKED','DELETED') |
| created_at | timestamptz | no | idx_users_created_at |
| last_seen_at | timestamptz | yes | idx_users_last_seen |

### 6.3 Таблиця `energy_state`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| user_id | bigint PK FK users(id) | no | PK |
| free_energy | smallint | no | check 0<=free_energy<=20 |
| paid_energy | integer | no | check paid_energy>=0 |
| free_cap | smallint | no | default 20 |
| regen_interval_sec | integer | no | default 1800 |
| last_regen_at | timestamptz | no | idx_energy_last_regen |
| last_daily_topup_local_date | date | no | idx_energy_topup_date |
| version | integer | no | default 0 |
| updated_at | timestamptz | no | - |

### 6.4 Таблиця `streak_state`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| user_id | bigint PK FK users(id) | no | PK |
| current_streak | integer | no | check current_streak>=0 |
| best_streak | integer | no | check best_streak>=0 |
| last_activity_local_date | date | yes | idx_streak_last_activity |
| today_status | varchar(16) | no | check in ('NO_ACTIVITY','PLAYED','FROZEN') |
| streak_saver_tokens | smallint | no | check streak_saver_tokens>=0 |
| streak_saver_last_purchase_at | timestamptz | yes | idx_streak_saver_purchase |
| premium_freezes_used_week | smallint | no | default 0 |
| premium_freeze_week_start_local_date | date | yes | - |
| version | integer | no | default 0 |
| updated_at | timestamptz | no | - |

### 6.5 Таблиця `purchases`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| id | uuid PK | no | PK |
| user_id | bigint FK users(id) | no | idx_purchases_user_created |
| product_code | varchar(32) | no | idx_purchases_product |
| product_type | varchar(16) | no | check in ('MICRO','PREMIUM','OFFER','REFERRAL_REWARD') |
| base_stars_amount | integer | no | check base_stars_amount>0 |
| discount_stars_amount | integer | no | default 0, check discount_stars_amount>=0 |
| stars_amount | integer | no | check stars_amount>0 |
| currency | varchar(3) | no | default 'XTR' |
| status | varchar(32) | no | check in ('CREATED','INVOICE_SENT','PRECHECKOUT_OK','PAID_UNCREDITED','CREDITED','FAILED','FAILED_CREDIT_PENDING_REVIEW','REFUNDED') |
| applied_promo_code_id | bigint FK promo_codes(id) | yes | idx_purchases_promo_code |
| idempotency_key | varchar(64) | no | UNIQUE |
| invoice_payload | varchar(128) | no | UNIQUE |
| telegram_payment_charge_id | varchar(128) | yes | UNIQUE |
| telegram_pre_checkout_query_id | varchar(128) | yes | UNIQUE |
| raw_successful_payment | jsonb | yes | - |
| created_at | timestamptz | no | - |
| paid_at | timestamptz | yes | - |
| credited_at | timestamptz | yes | - |
| refunded_at | timestamptz | yes | - |

CONSTRAINT:
- `check (stars_amount = greatest(1, base_stars_amount - discount_stars_amount))`.

### 6.6 Таблиця `ledger_entries`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| id | bigint PK | no | PK |
| user_id | bigint FK users(id) | no | idx_ledger_user_created |
| purchase_id | uuid FK purchases(id) | yes | idx_ledger_purchase |
| entry_type | varchar(32) | no | idx_ledger_type |
| asset | varchar(32) | no | check in ('FREE_ENERGY','PAID_ENERGY','PREMIUM','MODE_ACCESS','STREAK_SAVER') |
| direction | varchar(8) | no | check in ('CREDIT','DEBIT') |
| amount | integer | no | check amount>0 |
| balance_after | integer | yes | - |
| source | varchar(32) | no | - |
| idempotency_key | varchar(96) | no | UNIQUE |
| metadata | jsonb | no | default '{}'::jsonb |
| created_at | timestamptz | no | - |

### 6.7 Таблиця `entitlements`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| id | bigint PK | no | PK |
| user_id | bigint FK users(id) | no | idx_entitlements_user_type |
| entitlement_type | varchar(32) | no | check in ('PREMIUM','MODE_ACCESS','STREAK_SAVER_TOKEN','PREMIUM_AUTO_FREEZE') |
| scope | varchar(64) | yes | mode code / tier |
| status | varchar(16) | no | check in ('SCHEDULED','ACTIVE','EXPIRED','CONSUMED','REVOKED') |
| starts_at | timestamptz | no | idx_entitlements_starts |
| ends_at | timestamptz | yes | idx_entitlements_ends |
| source_purchase_id | uuid FK purchases(id) | yes | idx_entitlements_purchase |
| idempotency_key | varchar(96) | no | UNIQUE |
| metadata | jsonb | no | default '{}'::jsonb |
| created_at | timestamptz | no | - |
| updated_at | timestamptz | no | - |

UNIQUE partial indexes:
- `unique(user_id) where entitlement_type='PREMIUM' and status='ACTIVE'`.

### 6.8 Таблиця `mode_access`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| id | bigint PK | no | PK |
| user_id | bigint FK users(id) | no | idx_mode_access_user_mode |
| mode_code | varchar(32) | no | idx_mode_access_mode |
| source | varchar(16) | no | check in ('FREE','MEGA_PACK','PREMIUM') |
| starts_at | timestamptz | no | - |
| ends_at | timestamptz | yes | idx_mode_access_ends |
| status | varchar(16) | no | check in ('ACTIVE','EXPIRED','REVOKED') |
| source_purchase_id | uuid FK purchases(id) | yes | - |
| idempotency_key | varchar(96) | no | UNIQUE |
| created_at | timestamptz | no | - |

UNIQUE rule:
- `unique(user_id, mode_code, source, starts_at)`.

### 6.9 Таблиця `quiz_sessions`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| id | uuid PK | no | PK |
| user_id | bigint FK users(id) | no | idx_sessions_user_started |
| mode_code | varchar(32) | no | idx_sessions_mode |
| source | varchar(16) | no | check in ('MENU','DAILY_CHALLENGE','FRIEND_CHALLENGE','TOURNAMENT') |
| status | varchar(16) | no | check in ('STARTED','COMPLETED','ABANDONED','CANCELED') |
| energy_cost_total | integer | no | check energy_cost_total>=0 |
| started_at | timestamptz | no | - |
| completed_at | timestamptz | yes | - |
| local_date_berlin | date | no | idx_sessions_local_date |
| idempotency_key | varchar(96) | no | UNIQUE |

### 6.10 Таблиця `quiz_attempts`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| id | bigint PK | no | PK |
| session_id | uuid FK quiz_sessions(id) | no | idx_attempts_session |
| user_id | bigint FK users(id) | no | idx_attempts_user_time |
| question_id | varchar(64) | no | idx_attempts_question |
| is_correct | boolean | no | - |
| answered_at | timestamptz | no | - |
| response_ms | integer | no | check response_ms>=0 |
| idempotency_key | varchar(96) | no | UNIQUE |

### 6.11 Таблиця `offers_impressions`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| id | bigint PK | no | PK |
| user_id | bigint FK users(id) | no | idx_offers_user_time |
| offer_code | varchar(32) | no | idx_offers_code |
| trigger_code | varchar(32) | no | - |
| priority | smallint | no | - |
| shown_at | timestamptz | no | - |
| local_date_berlin | date | no | idx_offers_local_date |
| clicked_at | timestamptz | yes | - |
| converted_purchase_id | uuid FK purchases(id) | yes | - |
| dismiss_reason | varchar(32) | yes | - |
| idempotency_key | varchar(96) | no | UNIQUE |

### 6.12 Таблиця `promo_codes`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| id | bigint PK | no | PK |
| code_hash | char(64) | no | UNIQUE |
| code_prefix | varchar(8) | no | idx_promo_codes_prefix |
| campaign_name | varchar(128) | no | - |
| promo_type | varchar(32) | no | check in ('PREMIUM_GRANT','PERCENT_DISCOUNT') |
| grant_premium_days | smallint | yes | check grant_premium_days in (7,30,90) |
| discount_percent | smallint | yes | check discount_percent between 1 and 90 |
| target_scope | varchar(64) | no | idx_promo_codes_target |
| status | varchar(16) | no | check in ('ACTIVE','PAUSED','EXPIRED','DEPLETED') |
| valid_from | timestamptz | no | idx_promo_codes_valid_from |
| valid_until | timestamptz | no | idx_promo_codes_valid_until |
| max_total_uses | integer | yes | check max_total_uses>0 |
| used_total | integer | no | default 0, check used_total>=0 |
| max_uses_per_user | smallint | no | default 1, check max_uses_per_user=1 |
| new_users_only | boolean | no | default false |
| first_purchase_only | boolean | no | default false |
| created_by | varchar(64) | no | - |
| created_at | timestamptz | no | - |
| updated_at | timestamptz | no | - |

CONSTRAINT:
- `(promo_type='PREMIUM_GRANT' and grant_premium_days is not null and discount_percent is null) or (promo_type='PERCENT_DISCOUNT' and discount_percent is not null and grant_premium_days is null)`.
- `max_total_uses is null or used_total <= max_total_uses`.

### 6.13 Таблиця `promo_redemptions`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| id | uuid PK | no | PK |
| promo_code_id | bigint FK promo_codes(id) | no | idx_promo_redemptions_code |
| user_id | bigint FK users(id) | no | idx_promo_redemptions_user |
| status | varchar(16) | no | check in ('CREATED','VALIDATED','RESERVED','APPLIED','EXPIRED','REJECTED','REVOKED') |
| reject_reason | varchar(64) | yes | - |
| reserved_until | timestamptz | yes | idx_promo_redemptions_reserved_until |
| applied_purchase_id | uuid FK purchases(id) | yes | UNIQUE |
| grant_entitlement_id | bigint FK entitlements(id) | yes | UNIQUE |
| idempotency_key | varchar(96) | no | UNIQUE |
| validation_snapshot | jsonb | no | default '{}'::jsonb |
| created_at | timestamptz | no | - |
| applied_at | timestamptz | yes | - |
| updated_at | timestamptz | no | - |

UNIQUE rule:
- `unique(promo_code_id, user_id)`.

### 6.14 Таблиця `promo_attempts`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| id | bigint PK | no | PK |
| user_id | bigint FK users(id) | no | idx_promo_attempts_user_time |
| normalized_code_hash | char(64) | no | idx_promo_attempts_code_time |
| result | varchar(24) | no | check in ('ACCEPTED','INVALID','EXPIRED','NOT_APPLICABLE','RATE_LIMITED') |
| source | varchar(16) | no | check in ('COMMAND','BUTTON','API') |
| attempted_at | timestamptz | no | - |
| metadata | jsonb | no | default '{}'::jsonb |

### 6.15 Таблиця `referrals`

| Поле | Тип | Null | Індекси/Constraints |
|---|---|---|---|
| id | bigint PK | no | PK |
| referrer_user_id | bigint FK users(id) | no | idx_referrals_referrer |
| referred_user_id | bigint FK users(id) | no | UNIQUE |
| referral_code | varchar(16) | no | idx_referrals_code |
| status | varchar(24) | no | check in ('STARTED','QUALIFIED','REWARDED','REJECTED_FRAUD','CANCELED','DEFERRED_LIMIT') |
| qualified_at | timestamptz | yes | - |
| rewarded_at | timestamptz | yes | - |
| fraud_score | numeric(5,2) | no | default 0 |
| created_at | timestamptz | no | - |

CONSTRAINT:
- `check (referrer_user_id <> referred_user_id)`.
- `unique(referrer_user_id, referred_user_id)`.

### 6.16 Додаткові технічні таблиці (обов'язкові)

- `processed_updates(update_id bigint unique, processed_at timestamptz, status)`.
- `outbox_events(id bigserial, event_type, payload jsonb, status, created_at)`.
- `reconciliation_runs(id, started_at, finished_at, status, diff_count)`.
- `promo_code_batches(id bigserial, batch_name, created_by, created_at, total_codes, metadata jsonb)`.

### 6.17 Приклади записів

```sql
-- users
INSERT INTO users (id, telegram_user_id, username, language_code, timezone, referral_code, referred_by_user_id, status, created_at, last_seen_at)
VALUES (101, 777000111, 'anna_de', 'de', 'Europe/Berlin', 'A9QK2M', null, 'ACTIVE', now(), now());

-- energy_state
INSERT INTO energy_state (user_id, free_energy, paid_energy, free_cap, regen_interval_sec, last_regen_at, last_daily_topup_local_date, version, updated_at)
VALUES (101, 12, 15, 20, 1800, '2026-02-17T18:30:00Z', '2026-02-17', 3, now());

-- promo_codes
INSERT INTO promo_codes (id, code_hash, code_prefix, campaign_name, promo_type, grant_premium_days, target_scope, status, valid_from, valid_until, max_total_uses, used_total, max_uses_per_user, new_users_only, first_purchase_only, created_by, created_at, updated_at)
VALUES (301, '9f4f1f5f6f4f850f8e95a5f1493fe7b8130f0c2f7fc07b88bde8d5f209dd8f88', 'WELC', 'WELCOME_7D', 'PREMIUM_GRANT', 7, 'PREMIUM_ALL', 'ACTIVE', '2026-02-01T00:00:00Z', '2026-03-01T00:00:00Z', 10000, 1240, 1, false, true, 'admin', now(), now());

-- purchases
INSERT INTO purchases (id, user_id, product_code, product_type, base_stars_amount, discount_stars_amount, stars_amount, currency, status, applied_promo_code_id, idempotency_key, invoice_payload, telegram_payment_charge_id, telegram_pre_checkout_query_id, raw_successful_payment, created_at, paid_at, credited_at, refunded_at)
VALUES ('9bb9c0d1-77a8-45ef-95c6-7de9f148f0b4', 101, 'MEGA_PACK_15', 'MICRO', 15, 0, 15, 'XTR', 'CREDITED', null, 'idem_101_mp_20260217_1', 'inv_9bb9c0d1', 'tgch_12345', 'pcq_987', '{...}', now(), now(), now(), null);

-- ledger_entries
INSERT INTO ledger_entries (id, user_id, purchase_id, entry_type, asset, direction, amount, balance_after, source, idempotency_key, metadata, created_at)
VALUES (50001, 101, '9bb9c0d1-77a8-45ef-95c6-7de9f148f0b4', 'PURCHASE_CREDIT', 'PAID_ENERGY', 'CREDIT', 15, 30, 'PURCHASE', 'ledger_101_mp_1', '{}', now());

-- entitlements
INSERT INTO entitlements (id, user_id, entitlement_type, scope, status, starts_at, ends_at, source_purchase_id, idempotency_key, metadata, created_at, updated_at)
VALUES (9001, 101, 'MODE_ACCESS', 'CASES_PRACTICE', 'ACTIVE', '2026-02-17T19:01:10Z', '2026-02-18T19:01:10Z', '9bb9c0d1-77a8-45ef-95c6-7de9f148f0b4', 'ent_101_cases_1', '{}', now(), now());
```

---

## 7) Payments (Telegram Stars) — критичний розділ

### 7.1 Потік платежу

1. User натискає кнопку покупки.
2. Backend визначає фінальну ціну:
   - без promo: `stars_amount = base_stars_amount`;
   - з promo discount: `stars_amount = final_price` за `РІШЕННЯ SPEC-PROMO-04`.
3. Backend створює `purchase` у статусі `CREATED` із зафіксованими `base_stars_amount`, `discount_stars_amount`, `stars_amount`.
4. Якщо застосовано discount promo, `promo_redemption` переводиться у `RESERVED` до `reserved_until`.
5. Bot викликає `sendInvoice` (currency `XTR`, payload=`invoice_payload`).
6. Telegram надсилає `pre_checkout_query` -> backend валідує purchase, ціну, доступність.
7. Backend відповідає `answerPreCheckoutQuery(ok=true)`.
8. Telegram надсилає `successful_payment` update.
9. Backend у транзакції переводить purchase у `PAID_UNCREDITED` -> `CREDITED`, пише ledger, створює entitlement.
10. Якщо purchase пов'язаний із promo discount, `promo_redemption` -> `APPLIED`.
11. User отримує success-message.

### 7.2 Підтвердження

- Джерело істини для credit: `successful_payment` + унікальний `telegram_payment_charge_id`.
- `pre_checkout_query` не є фінальним підтвердженням грошей.

### 7.3 Ідемпотентність (exactly-once credit)

- Гарантія exactly-once на рівні DB:
  - unique `telegram_payment_charge_id`.
  - unique `purchases.idempotency_key`.
  - unique `ledger_entries.idempotency_key`.
- Усі credit операції в одній ACID транзакції.

### 7.4 Ledger accounting

Для кожної покупки обов'язково:
- `ledger_entries` CREDIT на відповідний asset.
- Для refund/reversal — компенсуючий DEBIT.
- Ledger immutable: оновлення існуючого рядка заборонене, тільки новий entry.

### 7.5 Refund / chargeback policy

`РІШЕННЯ SPEC-PAY-01`: підтримується policy-driven refund у випадках:
- технічний збій, коли entitlement не можна відновити коректно.
- дубль-списання за межами idempotency гарантії (аварійний кейс).

Процес refund:
1. Адмін/автоматична політика створює `refund_request`.
2. Виклик Telegram API `refundStarPayment`.
3. При успіху:
   - purchase -> `REFUNDED`;
   - записується компенсуючий `DEBIT` у ledger;
   - якщо entitlement активний/запланований -> `REVOKED`;
   - якщо entitlement вже `EXPIRED` або `CONSUMED` -> додається запис `REFUND_DEBT` у ledger для аудиту фінансового розриву.
4. Якщо entitlement уже частково спожито, policy робить часткове/повне ручне рішення і лог у `metadata`.

`РІШЕННЯ SPEC-PAY-02`: автоматичних chargeback від зовнішнього PSP немає в моделі; всі зовнішні ревізії проходять через reconciliation + manual review queue.

### 7.6 Відновлення після падіння сервера

- Recovery job кожні `5 хв` шукає `PAID_UNCREDITED` старше `2 хв`.
- Для кожного запису виконує повторний `apply_credit` idempotent.
- Якщо 3 спроби неуспішні -> `FAILED_CREDIT_PENDING_REVIEW` + alert + manual review queue.
- Мапінг станів: `FAILED_CREDIT_PENDING_REVIEW` у таблиці `purchases` відповідає state machine стану `P_CREDIT_REVIEW`.

### 7.7 Reconciliation job (звірка транзакцій)

- Розклад: кожні `15 хв` + щоденна повна звірка о `03:30 Berlin`.
- Перевіряє:
  - `paid purchases count` vs `credited ledger entries`.
  - `sum(stars_amount)` vs `sum(ledger credits)` по продуктам.
  - відсутність `PAID_UNCREDITED` > 30 хв.
- Результат в `reconciliation_runs` + alerts при `diff_count > 0`.

### 7.8 Edge cases

- Telegram прислав `successful_payment` раніше, ніж збережено `PRECHECKOUT_OK` (гонка) -> дозволити credit за наявності валідного `invoice_payload`.
- Дубль `pre_checkout_query` -> відповідати детерміновано, статус не ламати.
- User ініціював оплату, але не завершив -> `CREATED/INVOICE_SENT` експірується через 30 хв у `FAILED`.
- Discount promo зарезервовано, але платіж не завершено до `reserved_until` -> redemption `EXPIRED`, invoice заборонено оплатити повторно (створюється новий purchase).

### 7.9 Promo discount settlement

- Пара `purchase + promo_redemption` зв'язується однозначно через `promo_redemptions.applied_purchase_id` (UNIQUE).
- На `pre_checkout_query` валідується, що:
  - сума invoice == `purchase.stars_amount`;
  - promo still applicable до цього purchase;
  - `reserved_until > now_utc`.
- При успішній оплаті:
  - `promo_codes.used_total += 1`;
  - `promo_redemption.status='APPLIED'`.
- При refund purchase:
  - `promo_redemption.status='REVOKED'`;
  - `promo_codes.used_total` не декрементується (аудитно-фінансова консервативна модель).

---

## 8) API / Handlers

### 8.1 HTTP endpoints

1. `POST /webhook/telegram`
- Приймає Telegram `Update`.
- Відповідь: `200 OK` завжди після базової валідації + enqueue.

2. `POST /internal/game/start`
- Request:
```json
{
  "user_id": 101,
  "mode_code": "QUICK_MIX_A1A2",
  "client_nonce": "a1b2c3"
}
```
- Правило: `client_nonce` є idempotency ключем старту runtime-сесії.
- Response:
```json
{
  "session_id": "uuid",
  "energy_before": {"free": 12, "paid": 3},
  "energy_after": {"free": 11, "paid": 3},
  "question": {"id": "q_123", "text": "..."}
}
```

3. `POST /internal/game/answer`
- Request:
```json
{
  "session_id": "uuid",
  "question_id": "q_123",
  "selected_option": 2,
  "client_nonce": "ans_1"
}
```
- Response:
```json
{
  "is_correct": true,
  "streak": {"current": 9, "best": 12},
  "next_action": "NEXT_QUESTION"
}
```

4. `POST /internal/purchase/init`
- Request:
```json
{
  "user_id": 101,
  "product_code": "MEGA_PACK_15",
  "promo_redemption_id": null,
  "idempotency_key": "buy_101_20260217_1901"
}
```
- Response:
```json
{
  "purchase_id": "uuid",
  "invoice_payload": "inv_uuid",
  "pricing": {
    "base_stars_amount": 15,
    "discount_stars_amount": 0,
    "final_stars_amount": 15
  },
  "telegram_invoice": {"currency": "XTR", "amount": 15}
}
```

5. `POST /internal/purchase/apply-credit`
- Викликається з webhook handler після `successful_payment`.

6. `POST /internal/entitlements/apply`
- Сервісний endpoint для scheduler/recovery.

7. `GET /internal/menu`
- Формує актуальний стан меню (energy, streak, locked modes, offers).

8. `GET /health`, `GET /ready`

9. `POST /internal/promo/redeem`
- Request:
```json
{
  "user_id": 101,
  "promo_code": "WILLKOMMEN-50",
  "idempotency_key": "promo_101_20260217_2015"
}
```
- Response (grant):
```json
{
  "redemption_id": "uuid",
  "result_type": "PREMIUM_GRANT",
  "premium_days": 7,
  "premium_ends_at": "2026-02-24T20:15:00Z"
}
```
- Response (discount):
```json
{
  "redemption_id": "uuid",
  "result_type": "PERCENT_DISCOUNT",
  "discount_percent": 50,
  "reserved_until": "2026-02-17T20:30:00Z",
  "target_scope": "PREMIUM_MONTH"
}
```

### 8.2 Telegram handlers

- `/start`
- `callback:play`
- `callback:mode:<mode_code>`
- `callback:daily_challenge`
- `callback:answer:<session_id>:<option_idx>`
- `callback:buy:<product_code>`
- `callback:promo:open`
- `callback:offer:dismiss:<impression_id>`
- `callback:referral:open`
- `callback:referral:reward:<reward_code>`
- `/promo <code>`
- `/referral`
- `/invite`
- `pre_checkout_query`
- `message.successful_payment`

### 8.3 Error codes

| Code | HTTP | Значення | Retry |
|---|---:|---|---|
| E_ENERGY_INSUFFICIENT | 409 | Немає енергії для старту | ні |
| E_MODE_LOCKED | 403 | Режим locked | ні |
| E_PURCHASE_DUPLICATE | 409 | Ідемпотентний дубль покупки | ні |
| E_PAYMENT_NOT_CONFIRMED | 409 | Нема successful_payment | так |
| E_STREAK_SAVER_LIMIT | 429 | Saver вже куплений у вікні 7 днів | ні |
| E_PREMIUM_DOWNGRADE_NOT_ALLOWED | 422 | Спроба купити нижчий tier під час активного вищого | ні |
| E_PROMO_INVALID | 404 | Промокод не існує | ні |
| E_PROMO_EXPIRED | 410 | Промокод неактивний/закінчився | ні |
| E_PROMO_ALREADY_USED | 409 | Промокод уже використано користувачем | ні |
| E_PROMO_NOT_APPLICABLE | 422 | Промокод не підходить для цього продукту | ні |
| E_PROMO_RATE_LIMITED | 429 | Ліміт спроб введення промокоду | так |
| E_CONFLICT_VERSION | 409 | Оптимістичний конфлікт версії рядка | так |
| E_INTERNAL_TRANSIENT | 503 | Тимчасова помилка сервера | так |

### 8.4 Retry policy

- Внутрішні transient помилки: exponential backoff `250ms, 1s, 3s`, max 3.
- Purchase credit retries: max `3` спроби (1 спроба на цикл `recover_paid_uncredited`, кожні 5 хв), далі `FAILED_CREDIT_PENDING_REVIEW` + manual review.
- Telegram API `429`: враховувати `retry_after`.

---

## 9) Scheduling & Time

### 9.1 Timezone

- Бізнес-таймзона: `Europe/Berlin`.
- Зберігання часу: UTC.
- Локальна дата для бізнес-правил обчислюється через IANA timezone DB.

### 9.2 Daily reset

- Free daily top-up, daily challenge ліміти, streak rollover прив'язані до `00:00:00 Berlin`.
- Реалізація: lazy reset on user interaction + нічний consistency job.

### 9.3 Regen tick

- Базовий крок: 1800 сек.
- `ticks = floor((now_utc - last_regen_at) / 1800)`.
- Частковий залишок секунд переноситься до наступного обчислення.

### 9.4 DST правила

- Денні правила базуються на локальній даті, не на довжині дня в годинах.
- 24h entitlement рахується рівно 86,400 сек у UTC.

### 9.5 Точність таймерів і округлення

- Внутрішні обчислення: секунди.
- UI countdown: хвилини.
- Округлення для UI: `minutes_left = ceil(seconds_left / 60)`.
- Якщо `seconds_left < 60` -> текст `unter 1 Min.`.
- Для `full recovery`:
  - `sec_to_cap = (20 - free_energy) * 1800`.
  - `sec_to_midnight = next_berlin_midnight - now_utc`.
  - показуємо `min(sec_to_cap, sec_to_midnight)`.

### 9.6 Edge cases

- Серверний час дрейфнув: NTP sync обов'язковий; при відхиленні >2 сек -> alert.
- Cron job пропущено під час deploy: lazy reset гарантує коректність при першій взаємодії.

### 9.7 Promo scheduling

- Job `promo_reservation_expiry` виконується кожну `1 хв`:
  - `promo_redemptions.status='RESERVED' and reserved_until<=now` -> `EXPIRED`.
- Job `promo_campaign_status_rollover` виконується кожні `10 хв`:
  - `status ACTIVE` -> `EXPIRED`, якщо `valid_until<=now`.
  - `status ACTIVE` -> `DEPLETED`, якщо `max_total_uses is not null and used_total>=max_total_uses`.

---

## 10) Anti-Abuse & Security

### 10.1 Spam / click-farming

- Per-user rate limit + debounce callback.
- Offer click farming: `offers_impressions` + унікальний `idempotency_key`.
- Purchase button lock: одна активна invoice 1 продукт/користувач.

### 10.2 Multi-account

- Referral rewards тільки після кваліфікації за активністю.
- Velocity/fraud scoring.
- Ліміти на referral rewards/місяць.

### 10.3 Replay updates

- `processed_updates.update_id` UNIQUE.
- Повторний update -> `ACK + no-op`.

### 10.4 Race conditions

- `consume_energy` у транзакції `SELECT ... FOR UPDATE` на `energy_state`.
- `apply_credit` у транзакції `SELECT ... FOR UPDATE` на `purchases`.
- Version check (`version` increment) для optimistic conflict detect.

### 10.5 Додаткові mitigations

- Secret token в webhook.
- Admin endpoints тільки через allowlist + token auth.
- JSON schema validation на всі internal payloads.
- Audit log для manual adjustments.

### 10.6 Edge cases

- Два worker-и одночасно взяли ту саму recovery job -> advisory lock на `purchase_id`.
- Повторне натискання buy під лагом мережі -> idem key зі сторони клієнтської callback-сесії.
- Дубль `referral:reward:<reward_code>` callback -> перший успішний claim видає reward, повторний повертає `NO_REWARD` (без подвійного grant).
- Race `run_reward_distribution(reward_code=None)` vs user claim -> `SELECT ... FOR UPDATE` на referral rows гарантує консистентний одноразовий grant.

### 10.7 Promo anti-abuse

- Зберігання кодів: тільки `code_hash = HMAC_SHA256(normalized_code, PROMO_SECRET_PEPPER)`.
- Ліміт невдалих promo-спроб:
  - `5` невдалих спроб / користувач / 24 год.
  - після `5` -> блок вводу на `60 хв`.
- Глобальний захист:
  - якщо один `normalized_code_hash` має >100 невдалих спроб за 10 хв з різних user_id -> авто-pause кампанії та alert.
- Успішний redeem завжди ідемпотентний через `promo_redemptions.idempotency_key` + `unique(promo_code_id, user_id)`.

---

## 11) Observability & Ops

### 11.1 Structured logs

Мінімальні поля:
- `timestamp`
- `level`
- `service`
- `request_id`
- `user_id`
- `update_id`
- `purchase_id`
- `event_name`
- `result`
- `latency_ms`

### 11.2 Metrics

Продуктові:
- `DAU`, `WAU`, `MAU`
- `Free->Micro conversion`
- `Micro->Premium conversion`
- `ARPU`, `LTV`
- `Churn D1/D7/D30`
- `Purchase rate`
- `Offer CTR`
- `Promo redemption rate`
- `Promo -> Paid conversion`

Технічні:
- `webhook_rps`, `webhook_p95_ms`
- `db_tx_p95_ms`, `db_lock_wait_ms`
- `queue_depth`, `queue_lag_sec`
- `payment_credit_failures`
- `idempotency_conflicts`
- `promo_redeem_failures`
- `promo_bruteforce_blocks`

### 11.3 Alerts

- `webhook_error_rate > 2%` 5 хв.
- `queue_lag_sec > 120` для `q_high`.
- `PAID_UNCREDITED > 0` старше 10 хв.
- `db_cpu > 85%` 10 хв.
- `backup_age > 26 год`.
- `promo_redeem_failures_rate > 10%` 15 хв.
- `promo_bruteforce_blocks > 50` за 1 год.

### 11.4 Dashboards

- `Executive Monetization`: conversion, ARPU, revenue by product.
- `Promo Performance`: redemptions, grants, discount usage, promo revenue lift.
- `Gameplay Health`: starts, completions, energy zero events, streak losses.
- `Payments Reliability`: paid vs credited, refunds, reconciliation diffs.
- `Infra`: RPS, latencies, queue lag, errors.

### 11.5 Backups + restore drill

- Щоденний full backup + WAL.
- Щотижневий автоматичний restore на staging.
- Чеклист drill:
  1. restore DB.
  2. run миграції.
  3. execute smoke tests (play, buy, credit).
  4. звірка контрольних сум таблиць.

---

## 12) Testing Strategy

### 12.1 Unit tests для state machines

Обов'язкові покриття:
- Energy SM переходи.
- Streak SM переходи.
- Purchase SM transitions.
- Entitlement SM transitions.
- Promo Redemption SM transitions.

Критерій:
- 100% transition coverage по таблицях переходів.

### 12.2 Integration tests для payments

Сценарії:
1. `sendInvoice -> pre_checkout -> successful_payment -> credit`.
2. duplicate `successful_payment` x3.
3. server crash після `PAID_UNCREDITED`.
4. refund flow із compensating ledger.
5. reconciliation виявляє і виправляє розбіжність.
6. promo discount -> purchase init -> successful payment -> redemption applied.
7. promo grant -> premium entitlement issue -> expiry.

### 12.3 Load tests (план)

Інструмент: `k6`.

Профілі:
- `steady`: 80 rps, 30 хв.
- `peak`: 300 rps, 10 хв.
- `burst`: 600 rps 30 сек.

Умови успіху:
- webhook p95 <= 800ms.
- помилки <1% (без урахування штучних rate-limit відповідей).
- відсутність double debit / double credit.

### 12.4 Property-based tests для ідемпотентності

Генеруємо довільні послідовності подій (дублікати, reorder, retries) і перевіряємо інваріанти:
- `credits_applied_once_per_charge_id`.
- `energy_never_negative`.
- `streak_non_negative`.
- `ledger_balance_consistent`.
- `promo_redeemed_once_per_user_code`.

### 12.5 Edge cases test list

- DST boundary на streak.
- Midnight reset + active gameplay.
- Premium expiry during session.
- Concurrent buy clicks.
- Concurrent play from 2 devices.
- Concurrent promo redeem from 2 devices.
- Promo brute-force throttle.

---

## 13) Step-by-step Implementation Plan (Milestones)

### Milestone 1: Foundation & Infra

Що робимо:
- FastAPI webhook skeleton, Postgres, Redis, Celery, CI/CD, secrets.

DoD:
- `/health`, `/ready` працюють.
- webhook валідує secret token.

Ризики + перевірка:
- ризик помилкової мережевої конфігурації -> integration smoke via Telegram sandbox webhook.

### Milestone 2: Core Data Model

Що робимо:
- Міграції всіх таблиць розділу 6.
- Базові репозиторії + constraints.

DoD:
- всі unique/check/fk застосовані.
- міграції проходять up/down на staging.

Ризики + перевірка:
- ризик блокувань під час міграцій -> zero-downtime rehearsal.

### Milestone 3: Energy Engine

Що робимо:
- consume, regen, daily top-up, energy timers.

DoD:
- unit tests для Energy SM 100% transition coverage.
- negative energy неможливий.

Ризики + перевірка:
- race double-spend -> concurrency tests з 100 паралельними стартами.

### Milestone 4: Streak Engine

Що робимо:
- daily activity tracking, saver, auto-freeze, rollover.

DoD:
- unit tests для Streak SM.
- DST test cases зелені.

Ризики + перевірка:
- timezone edge bugs -> fixed-date simulation suite.

### Milestone 5: Free Tier Gameplay Handlers

Що робимо:
- `/start`, menu, start/answer flow, locked checks, daily challenge exemption.

DoD:
- користувач проходить повний free loop.
- locked режими коректно upsell-яться.

Ризики + перевірка:
- UI callback дублікати -> idem tests.

### Milestone 6: Telegram Stars Micro Purchases

Що робимо:
- invoice, pre-checkout, successful_payment, apply_credit, ledger.

DoD:
- exactly-once credit підтверджено integration tests.
- recovery job закриває `PAID_UNCREDITED`.

Ризики + перевірка:
- payment event reordering -> chaos tests з reordered webhook payloads.

### Milestone 7: Premium Entitlements

Що робимо:
- premium plans, upgrade rules, expiry behavior, mode access resolution.

DoD:
- всі 4 premium плани працюють за цінами/періодами.
- downgrade block і upgrade extension покриті тестами.

Ризики + перевірка:
- логіка перетинів premium+mega -> matrix integration tests.

### Milestone 8: Offers & Triggers

Що робимо:
- trigger engine, anti-spam frequency caps, priority resolver.

DoD:
- deterministic offer selection при множинних тригерах.
- offers_impressions пишуться idempotent.

Ризики + перевірка:
- overspam -> simulation на synthetic user timeline.

### Milestone 9: Referral & Anti-Fraud

Що робимо:
- referral tracking, qualification, rewards, fraud scoring.

DoD:
- reward slot стає claimable тільки після qualification + delay 48h, видача reward лише через user choice callback.
- self-ref і cyclic-ref заблоковані.
- duplicate reward-choice callback не дає подвійної видачі (idempotent behavior).

Ризики + перевірка:
- false positives fraud -> review dashboard + threshold tuning.

### Milestone 10: Promo Codes Module

Що робимо:
- promo code generation/import, redeem API, discount quote, premium grant flow, anti-abuse throttling.

DoD:
- `PROMO_PREMIUM_GRANT` (7/30/90) працює end-to-end.
- `PROMO_PERCENT_DISCOUNT` коректно фіксує ціну і проходить через Telegram Stars payment flow.
- ідемпотентність promo redemption підтверджена інтеграційними тестами.

Ризики + перевірка:
- brute-force code guessing -> load + abuse simulation, перевірка блокувань.

### Milestone 11: Observability, Reconciliation, Runbooks

Що робимо:
- dashboards, alerts, reconciliation jobs, backup/restore runbooks.

DoD:
- ключові alert-и тригеряться в staging drills.
- reconciliation diff=0 у нормальному сценарії.

Ризики + перевірка:
- шумні алерти -> SLO-based tuning.

### Milestone 12: Load & Release

Що робимо:
- k6 load, capacity tuning, canary release 5% -> 25% -> 100%.

DoD:
- NFR latency/availability цілі виконані.
- rollback план перевірений.

Ризики + перевірка:
- несподіваний Telegram 429 ріст -> throttling validation під peak.

### Agent Handoff Protocol (обов'язково)

Після кожного milestone команда фіксує артефакти:
1. `docs/milestones/M{N}_summary.md`:
   - що реалізовано;
   - що не реалізовано;
   - відкриті ризики;
   - рішення, які відхиляються від SPEC (якщо є).
2. `docs/milestones/M{N}_db_changes.md`:
   - список міграцій;
   - rollback-інструкція;
   - сумісність із попередньою версією.
3. `docs/milestones/M{N}_tests.md`:
   - список тестів;
   - покриття state machines;
   - результати load/chaos (якщо застосовно).
4. `docs/milestones/M{N}_ops.md`:
   - нові алерти;
   - dashboard changes;
   - runbook updates.

`РІШЕННЯ SPEC-HANDOFF-01`: наступний агент починає роботу лише після читання останнього `M{N}_summary.md` і перевірки невиконаних пунктів.

---

## 14) Appendix: German UI Copy

| message_id | text | buttons |
|---|---|---|
| msg.home.title | Willkommen bei Quiz Arena. | Spielen; Daily Challenge; Pakete; Premium |
| msg.home.energy | Energie: {free_energy}/20 + {paid_energy} Bonus. | - |
| msg.home.next_regen | Nächste Aufladung in {minutes} Min. | - |
| msg.energy.empty.title | Deine Energie ist leer. | - |
| msg.energy.empty.body | Du brauchst 1⚡ pro Quiz. Warte oder hol dir ein Paket. | Warten; ⚡ +10 Energie (10⭐); 📦 Mega Pack (15⭐); 💎 Premium; 🎯 Daily Challenge |
| msg.energy.low.banner | Nur noch {energy}⚡. Willst du +10⚡ für 10⭐? | Jetzt holen |
| msg.locked.mode | Dieser Modus ist gesperrt. | 📦 Mega Pack; 💎 Premium; Zurück |
| msg.daily.challenge.free | Daily Challenge ist heute kostenlos. | Starten |
| msg.purchase.energy10.offer | Sofort weiterspielen? Hol dir +10 Energie für 10⭐. | Kaufen; Später |
| msg.purchase.megapack.offer | Mega Pack: +15⚡ und 3 Modi für 24 Stunden für 15⭐. | Kaufen; Details |
| msg.purchase.streaksaver.offer | Schütze deine Serie für einen Tag mit Streak Saver für 20⭐. | Kaufen; Später |
| msg.purchase.success.energy10 | Erfolg! +10 Energie wurde gutgeschrieben. | Weiter spielen |
| msg.purchase.success.megapack | Mega Pack aktiv. +15 Energie und 3 Modi sind jetzt freigeschaltet. | Modus wählen |
| msg.purchase.success.streaksaver | Streak Saver ist bereit. Ein Fehltag wird automatisch geschützt. | Verstanden |
| msg.purchase.error.duplicate | Diese Zahlung wurde bereits verarbeitet. | OK |
| msg.purchase.error.failed | Zahlung fehlgeschlagen. Bitte versuche es erneut. | Erneut; Zurück |
| msg.promo.input.hint | Gib deinen Promo-Code ein. | Code senden; Abbrechen |
| msg.promo.success.grant | Promo-Code aktiviert. Premium wurde freigeschaltet. | Super |
| msg.promo.success.discount | Promo-Code akzeptiert. Dein Rabatt ist 15 Minuten reserviert. | Jetzt kaufen |
| msg.promo.error.invalid | Dieser Promo-Code ist ungültig. | Erneut; Zurück |
| msg.promo.error.expired | Dieser Promo-Code ist abgelaufen. | OK |
| msg.promo.error.used | Du hast diesen Promo-Code bereits verwendet. | OK |
| msg.promo.error.not_applicable | Dieser Promo-Code passt nicht zu diesem Produkt. | OK |
| msg.promo.error.rate_limited | Zu viele Versuche. Bitte versuche es später erneut. | OK |
| msg.premium.menu.title | Premium ohne Limits. Wähle deinen Plan. | Starter; Month; Season; Year |
| msg.premium.starter | Premium Starter: 7 Tage für 29⭐. | Kaufen |
| msg.premium.month | Premium Month: 30 Tage für 99⭐. | Kaufen |
| msg.premium.season | Premium Season: 90 Tage für 249⭐. | Kaufen |
| msg.premium.year | Premium Year: 365 Tage für 499⭐. | Kaufen |
| msg.premium.upgrade.success | Upgrade aktiv. Deine Premium-Zeit wurde verlängert. | Super |
| msg.premium.expired | Dein Premium ist abgelaufen. Du bist wieder im Free-Modus. | Pakete ansehen; Weiterspielen |
| msg.premium.downgrade.blocked | Ein niedrigerer Plan ist während aktivem Premium nicht verfügbar. | OK |
| msg.streak.status | Serie: {current_streak} Tage. | - |
| msg.streak.risk.22h | Deine Serie ist in Gefahr. Spiele jetzt oder sichere sie mit Streak Saver. | Jetzt spielen; Streak Saver |
| msg.streak.saved | Deine Serie wurde geschützt. | Weiter |
| msg.streak.lost | Deine Serie ist gerissen. Starte heute neu. | Spielen |
| msg.offer.energy.zero | Du bist leer. Spiele jetzt weiter mit +10⚡ oder Mega Pack. | ⚡ +10; 📦 Mega Pack; 💎 Premium |
| msg.offer.mega.after_second_energy | Du kaufst oft +10⚡. Mega Pack ist deutlich besser. | Mega Pack testen |
| msg.offer.locked.mode | Dieser Modus ist gesperrt. Mega Pack schaltet ihn 24 Stunden frei. | Mega Pack |
| msg.offer.comeback | Willkommen zurück. Heute: +20 Energie geschenkt und Mega Pack Rabatt. | Zurück ins Spiel |
| msg.offer.starter.to.month | Dein Starter ist vorbei. Mit Month bleibst du ohne Limits. | Month holen |
| msg.offer.month.to.season_year | Du spielst konstant. Season und Year sparen dir Sterne. | Season; Year; Month |
| msg.offer.flash.weekend | Flash-Angebot nur für kurze Zeit. | Jetzt nutzen |
| msg.referral.invite | Lade Freunde ein und verdiene Belohnungen. | Link teilen |
| msg.referral.progress | Dein Fortschritt: {qualified}/3 qualifizierte Freunde. | Weiter einladen |
| msg.referral.reward.choice | Du hast eine Belohnung erreicht. Wähle deinen Bonus. | Mega Pack; Premium Starter |
| msg.referral.link | Dein Einladungslink: {invite_link} | - |
| msg.referral.link.fallback | Teile diesen Start-Code: ref_{referral_code} | - |
| msg.referral.pending | Offene Belohnungen: {pending}. Jetzt wählbar: {claimable}. | - |
| msg.referral.next_reward_at | Nächste Belohnung verfügbar ab: {next_reward_at} (Berlin). | - |
| msg.referral.reward.claimed.megapack | Belohnung aktiviert: Mega Pack. | - |
| msg.referral.reward.claimed.premium | Belohnung aktiviert: Premium Starter. | - |
| msg.referral.reward.unavailable | Aktuell ist keine Belohnung verfügbar. | - |
| msg.referral.reward.too_early | Noch nicht freigeschaltet. Bitte warte auf den Delay. | - |
| msg.referral.reward.monthly_cap | Monatslimit erreicht. Neue Belohnungen folgen nächsten Monat. | - |
| msg.referral.rejected | Diese Einladung zählt nicht für Belohnungen. | Details |
| msg.error.generic | Etwas ist schiefgelaufen. Bitte erneut versuchen. | Erneut |
| msg.error.rate_limit | Zu schnell. Bitte kurz warten. | OK |
| msg.system.maintenance | Kurze Wartung. Bitte in ein paar Minuten wiederkommen. | OK |
