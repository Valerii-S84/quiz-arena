# DUELL + Turnier (v2) — Пріоритет виконання

## 1) Scope lock (обов'язково)
- Єдиний пріоритет: реалізація ТЗ `DUELL + Turnier (v2)`.
- Фаза 1 закрита (2026-02-27), працюємо у Фазі 2.
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

### 4.1 Фаза 1 (DUELL) — DONE
Закрито і вважається baseline для наступних фаз:
- `friend_challenges` приведено до DUELL v2 станів (`PENDING/ACCEPTED/CREATOR_DONE/OPPONENT_DONE/...`).
- Додано `challenge_type`, `question_ids`, `tournament_match_id`, `creator_finished_at`, `opponent_finished_at`.
- Питання фіксуються при створенні (`duel:<challenge_id>` seed), обидва гравці отримують однаковий порядок.
- Deep link `duel_<id>` підтримується в `/start`.
- Anti-abuse для DUELL присутній (`max active`, `max open`, `max/day`, `max push`).
- TTL-воркер працює для `PENDING` expiry і `ACCEPTED` walkover.
- Async proof-card рендер + кеш `file_id` реалізовано.
- Екран `Meine Duelle` і `Revanche` доступні.

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
- Базу будуємо на існуючому friend challenge engine як матч-движку.
- Для турнірів доцільно використовувати той самий duel engine як матч-движок (як у ТЗ), додавши orchestration layer.

## 6) План Фази 2 (Приватний турнір) — execution
Порядок строго відповідає ТЗ пп. 14-22.

1. Дані + міграція (`M32`)
- Таблиці: `tournaments`, `tournament_participants`, `tournament_matches`.
- Індекси для hot-path: `(tournament_id, round_no, status)`, `(invite_code)`, `(status, registration_deadline)`.
- Додаткові технічні поля для UX edit-message та proof-card кешу (за потреби, без зміни поведінки ТЗ).

2. Domain model + repo layer
- Нові моделі в `app/db/models/`: `tournaments.py`, `tournament_participants.py`, `tournament_matches.py`.
- Нові repo в `app/db/repo/`: CRUD, lock-safe join/start, вибір матчів раунду, оновлення таблиці.
- Оновити `app/db/models/__init__.py` і `app/db/repo/__init__.py`.

3. Tournament service (orchestration, без bot-логіки)
- Новий доменний шар `app/game/tournaments/`:
  - create/join/start tournament,
  - swiss pairing (3 rounds),
  - standings + tie-break,
  - bridge `tournament_match -> friend_challenge`.
- Матчі створюються через існуючий `friend_challenge` engine, без дубляжу quiz flow.

4. Bot UX для приватного турніру
- Замінити `Bald verfügbar` на повний flow:
  - створення (`format 5/12`),
  - share (`t.me/share/url`),
  - старт creator-ом при `>=2`,
  - deep link join `start=tournament_<code>`.
- Додати тексти/клавіатури DE для lobby, roster, start, table, share.

5. Worker round lifecycle (24h TTL на раунд)
- Окремий tournament worker:
  - закриття registration,
  - старт round 1/2/3,
  - дедлайн round + технічні поразки,
  - завершення турніру.
- Для кожного учасника leaderboard оновлюється через edit одного повідомлення.

6. Proof cards + sharing
- Async генерація карток для всіх учасників після завершення round 3.
- Топ-3 отримують special card (🥇🥈🥉), інші стандартну.
- Кеш `file_id` для повторної відправки.

7. Аналітика
- Події: `private_tournament_created`, `private_tournament_joined`,
  `private_tournament_started`, `private_tournament_completed`,
  `private_tournament_result_shared`.

8. Тести + gate
- Unit: swiss pairing, standings/tie-break, round transitions.
- Integration: create/join/start/3 rounds/ttl/walkover/final.
- Bot: callback/deep-link flows, table edit behavior.
- Обов'язковий gate:
  - `.venv/bin/ruff check .`
  - `.venv/bin/mypy .`
  - `DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test TMPDIR=/tmp .venv/bin/pytest -q`

## 7) Правило виконання на цю гілку
- Будь-яка нова зміна в `duel` має прямо мапитися на пункти ТЗ цієї ініціативи.
- Якщо зміна не входить в ТЗ `DUELL + Turnier (v2)`, вона відкладається.
