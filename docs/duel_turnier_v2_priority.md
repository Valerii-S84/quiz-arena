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
- База для турнірів реалізована: таблиці `tournaments`, `tournament_participants`, `tournament_matches`.
- Реалізовано orchestration service `create/join/start` + Swiss pairings + зв'язка `tournament_match -> friend_challenge`.
- Реалізовано round lifecycle worker (settle/advance/completion).
- Ще не реалізовано повний bot UX приватного турніру і таблицю з edit одного повідомлення.
- Ще не реалізовано proof cards та share результату приватного турніру.

### 4.3 Фаза 3 (Daily Arena Cup)
Стан:
- Нема daily cup домену (реєстрація 12:00-14:00, 3 раунди, фінал 20:00).
- Нема scheduler/config для daily cup time slots.
- Нема push для active users 7d, min participants=4, cancel flow.
- Нема daily cup proof cards за місцем.

## 5) Технічна реалізовність
- Реалізовно в поточній архітектурі.
- Базу будуємо на існуючому friend challenge engine як матч-движку.
- Для турнірів використовуємо той самий duel engine як матч-движок (як у ТЗ), додаючи orchestration layer.

## 6) План Фази 2 (Приватний турнір) — execution
Порядок строго відповідає ТЗ пп. 14-22.

1. Дані + міграція (`M32`) — зроблено.
2. Domain model + repo layer — зроблено.
3. Tournament service (orchestration, без bot-логіки) — зроблено.
4. Bot UX для приватного турніру — в роботі.
5. Worker round lifecycle (24h TTL на раунд) — зроблено (база).
6. Proof cards + sharing — pending.
7. Аналітика — частково.
8. Тести + gate — зелений для поточного інкременту.

## 7) Правило виконання на цю гілку
- Будь-яка нова зміна в `duel` має прямо мапитися на пункти ТЗ цієї ініціативи.
- Якщо зміна не входить в ТЗ `DUELL + Turnier (v2)`, вона відкладається.
