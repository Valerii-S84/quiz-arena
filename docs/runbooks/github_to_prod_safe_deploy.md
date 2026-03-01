# GitHub -> Production Safe Deploy (Quiz Arena)

Цей документ для наступного агента, щоб деплой проходив стабільно і без повторення інцидентів із "бот завис / не відповідає".

## 0. Інваріанти (обов'язково)
1. Деплой тільки з GitHub `main` (не з локального dirty-дерева).
2. На сервері використовується тільки реальний env: `/opt/quiz-arena/.env`.
3. Ніколи не запускати прод-команди з `.env.production.example` (там placeholder-и).
4. Міграції застосовувати тільки після валідного backup.
5. Після деплою обов'язково перевіряти health + webhook + Celery + Redis черги.

## 1. GitHub flow (перед сервером)
1. Створи гілку від `origin/main`.
2. Внеси зміни.
3. Прогін локального gate (тільки через venv):
```bash
.venv/bin/ruff check .
.venv/bin/mypy .
DATABASE_URL=postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test TMPDIR=/tmp .venv/bin/pytest -q
```
4. Push гілки і PR у `main`.
5. Дочекайся `CI / lint_unit` (і `integration`, якщо активний).
6. Merge PR у `main`.
7. Зафіксуй SHA merge-коміту:
```bash
git ls-remote --heads git@github.com:Valerii-S84/quiz-arena.git main
```

## 2. Перевірка правильного прод-хоста
1. Переконайся, що домен вказує на потрібний сервер:
```bash
dig +short deutchquizarena.de
```
2. Підключись SSH саме до цього IP.
3. На сервері перевір шлях:
```bash
cd /opt/quiz-arena
pwd
```

## 3. Safe sync коду на сервері
Варіант A (рекомендовано, якщо дерево dirty): clean reclone.

```bash
ssh root@<SERVER_IP>
set -euo pipefail
TS=$(date +%Y%m%d_%H%M%S)
cd /opt/quiz-arena
cp .env /opt/quiz-arena.env.$TS
cd /opt
mv quiz-arena quiz-arena_dirty_$TS
git clone --branch main --single-branch git@github.com:Valerii-S84/quiz-arena.git quiz-arena
cp /opt/quiz-arena.env.$TS /opt/quiz-arena/.env
cd /opt/quiz-arena
git rev-parse --short HEAD
```

Варіант B (тільки якщо дерево чисте):
```bash
cd /opt/quiz-arena
git fetch origin
git checkout main
git reset --hard origin/main
```

## 4. Backup перед міграціями
Через `postgres` сервіс (не `api`, бо там може не бути `pg_dump`):
```bash
cd /opt/quiz-arena
source /opt/quiz-arena/.env
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env \
  exec -T postgres sh -c 'pg_dump -U $POSTGRES_USER $POSTGRES_DB' \
  > /opt/quiz-arena/backup_pre_deploy_$(date +%Y%m%d_%H%M%S).sql
ls -lh /opt/quiz-arena/backup_pre_deploy_*.sql | tail -1
```

## 5. Build + deploy runtime
```bash
cd /opt/quiz-arena
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env up -d --build
```

## 6. Міграції
```bash
cd /opt/quiz-arena
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env \
  exec -T api sh -c "cd /app && alembic upgrade head"

docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env \
  exec -T api sh -c "cd /app && alembic current"
```

## 7. Обов'язкова post-deploy перевірка
1. Контейнери:
```bash
docker compose -f docker-compose.prod.yml ps
```
2. Health endpoint:
```bash
curl -sS https://deutchquizarena.de/health
```
Очікування: `status=ok`, `database=ok`, `redis=ok`, `celery=ok`.

3. Celery стан:
```bash
docker compose -f docker-compose.prod.yml exec -T worker celery -A app.workers.celery_app inspect active
docker compose -f docker-compose.prod.yml exec -T worker celery -A app.workers.celery_app inspect reserved
```
Очікування: без "залиплих" задач.

4. Redis черги:
```bash
docker compose -f docker-compose.prod.yml exec -T redis redis-cli LLEN q_normal
docker compose -f docker-compose.prod.yml exec -T redis redis-cli LLEN q_critical
docker compose -f docker-compose.prod.yml exec -T redis redis-cli LLEN q_low
```
Очікування: не ростуть безконтрольно.

5. Webhook:
```bash
source /opt/quiz-arena/.env
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```
Очікування: URL = `https://deutchquizarena.de/webhook/telegram`, `pending_update_count=0`, без `last_error_message`.

## 8. Duel-specific smoke (після інциденту обов'язково)
1. Перевірити worker-логи по ретраях:
```bash
docker compose -f docker-compose.prod.yml logs worker --tail 200 | \
  grep -E "telegram_update_retry_scheduled|telegram_update_failed_final|telegram_update_non_retryable_error|telegram_update_processed"
```
2. Переконатись, що немає циклічного спаму/ретраїв одного update.
3. Провести ручний сценарій у Telegram:
   - створення дуелі;
   - прийняття опонентом;
   - 1-2 відповіді;
   - перевірка, що кнопки відповідають у обох гравців.

## 9. Швидка діагностика якщо бот "висить"
1. Postgres lock/idle in transaction:
```bash
source /opt/quiz-arena/.env
docker compose -f docker-compose.prod.yml exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
"SELECT pid,state,wait_event_type,wait_event,now()-xact_start AS xact_age,left(query,180) AS query \
 FROM pg_stat_activity WHERE datname=current_database() AND state='idle in transaction' ORDER BY xact_start;"
```
2. Якщо всі воркери зайняті одними задачами, а черга росте: дивитись `process_telegram_update` і останні stacktrace.

## 10. Rollback (мінімальний)
1. Визнач останню стабільну директорію (наприклад `quiz-arena_dirty_<TS>`).
2. Атомарно поверни її:
```bash
cd /opt
mv quiz-arena quiz-arena_bad_$(date +%Y%m%d_%H%M%S)
mv quiz-arena_dirty_<TS> quiz-arena
cd /opt/quiz-arena
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env up -d --build
```
3. Якщо проблема в БД-схемі/даних, відновити dump.

## 11. Антипатерни (заборонено)
1. `--env-file .env.production.example` у прод-командах.
2. Команди `exec db ...` коли сервіс реально називається `postgres`.
3. Міграції без backup.
4. Деплой "поверх" дуже dirty git-дерева без backup/reclone.
5. Вважати "health ok" достатнім без перевірки webhook/черг/active задач.

