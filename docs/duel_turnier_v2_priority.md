# DUELL + Turnier (v2) — Пріоритет виконання

## 1) Scope lock (обов'язково)
- Єдиний пріоритет: реалізація ТЗ `DUELL + Turnier (v2)`.
- Поки не закрито всі критерії готовності Фази 1, не стартуємо Фазу 2.
- Поки не закрито всі критерії готовності Фази 2, не стартуємо Фазу 3.
- Інші задачі не беремо в роботу до повного завершення цього ТЗ.

## 2) Робоча гілка
- Активна гілка: `duel`.

## 3) Фазний план (fixed order)
1. Фаза 1: DUELL engine (основа).
2. Фаза 2: Приватний турнір.
3. Фаза 3: Daily Arena Cup.

Gate перед переходом між фазами:
- `.venv/bin/ruff check .`
- `.venv/bin/mypy .`
- `DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test TMPDIR=/tmp .venv/bin/pytest -q`

## 4) Поточний стан vs ТЗ (gap-аналіз)

### 4.1 Фаза 1 (DUELL)
Вже є:
- Базовий async friend challenge engine з deep link (`fc_<token>`), однаковими питаннями для обох гравців.
- Share через `t.me/share/url`.
- Rematch.
- TTL-воркер (нагадування + expiry).
- Аналітика friend challenge (частково).

Розбіжності з ТЗ:
- Схема `friend_challenges` інша: зараз `status=ACTIVE|COMPLETED|CANCELED|EXPIRED`, нема `PENDING|ACCEPTED|CREATOR_DONE|OPPONENT_DONE`, нема `challenge_type`, `question_ids`, `tournament_match_id`, `creator_finished_at`, `opponent_finished_at`.
- Зараз один TTL (24h за config), а потрібно 2 режими: `PENDING=6h`, `ACCEPTED=48h` + технічна поразка.
- Питання не фіксуються при створенні дуелі списком `question_ids`; вони фактично фіксуються по раунду при старті першого гравця.
- Нема розділення DUELL типів `DIRECT` vs `OPEN` в моделі/UX.
- Нема екрану `Meine Duelle` (DRAN/WARTET/OFFEN/ABGESCHLOSSEN).
- Нема anti-abuse з ТЗ: `max 10 active`, `1 active OPEN`, `max 20 new/day`.
- Нема async генерації графічної proof card (1080x1080, Pillow/html2image + кеш `file_id`); зараз proof card текстова.
- Нема push-логіки exactly за ТЗ для `PENDING -> EXPIRED` з CTA на OPEN і ліміту `max 2 push на дуель/юзера`.
- Deep link формат у ТЗ `duel_<id>`, зараз `fc_<token>`.
- Зараз є формат `3/5/12`, у ТЗ для DUELL: `QUICK_5` або `QUICK_12`.

### 4.2 Фаза 2 (Приватний турнір)
Стан:
- Нема таблиць `tournaments`, `tournament_participants`, `tournament_matches`.
- Нема tournament service, Swiss pairing, round worker, leaderboard edit-message, proof cards для кожного учасника.
- Нема deep link `tournament_<code>` і flow join/start.

### 4.3 Фаза 3 (Daily Arena Cup)
Стан:
- Нема daily cup домену (реєстрація 12:00-14:00, 3 раунди, фінал 20:00).
- Нема scheduler/config для daily cup time slots.
- Нема push для active users 7d, min participants=4, cancel flow.
- Нема daily cup proof cards за місцем.

## 5) Технічна реалізовність
- Реалізовно в поточній архітектурі.
- Базу можна будувати на існуючому friend challenge engine з міграцією статус-моделі та розширенням сервісів/воркерів.
- Для турнірів доцільно використовувати той самий duel engine як матч-движок (як у ТЗ), додавши orchestration layer.

## 6) Критичні рішення перед імплементацією (потрібне підтвердження)
1. Формат кнопок DUELL: прибираємо `SPRINT 3` повністю, лишаємо тільки `5/12`?
2. `DIRECT` в ТЗ: це персональний виклик конкретному опоненту чи фактично link-based invite (як зараз)?
3. TTL `ACCEPTED=48h` + технічна поразка: як рахувати фінальний score, якщо один не зіграв жодної відповіді?
4. Для `OPEN` при одночасному accept: залишаємо first-write-wins з row lock (очікувана поведінка)?
5. Onboarding по deep link для нового юзера: що вважаємо "≤3 кроки" формально (тексти/кнопки/екрани)?

## 7) Правило виконання на цю гілку
- Будь-яка нова зміна в `duel` має прямо мапитися на пункти ТЗ цієї ініціативи.
- Якщо зміна не входить в ТЗ `DUELL + Turnier (v2)`, вона відкладається.
