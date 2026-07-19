# GitHub → Production Safe Deploy — Quiz Arena backend

Цей runbook застосовується до поточного split-runtime: backend належить compose
project `quiz-arena`, frontend — `quiz-arena-site`, shared edge — `infra-caddy`.

## 0. Обов’язкові інваріанти

1. Deploy виконується тільки з commit, який уже merged у GitHub `main` і має
   green required CI.
2. API, worker і beat використовують один `BACKEND_IMAGE`, зібраний один раз з
   exact deploy commit.
3. Routine backend deploy не керує `frontend`, `caddy`, PostgreSQL, Redis,
   Docker volumes, DNS, webhook URL або payment config.
4. Production `.env` не відкривається і не друкується. Runbook перевіряє лише
   existence/readability та передає path Docker Compose.
5. Dirty production checkout не очищається через `reset`, `clean` або overwrite.
   Новий код готується в окремому release checkout.
6. Якщо live Alembic revision не збігається з candidate head, deploy
   зупиняється до окремого migration/rollback approval.
7. До recreate API compose має пройти durable network preflight для
   `quiz-arena-edge` з alias `api`.
8. Одночасно має працювати рівно один Celery beat.

## 1. GitHub gate

Локально або в CI:

```bash
bash scripts/local_ci.sh
git diff --check origin/main...HEAD
```

Перед сервером зафіксувати merged commit:

```bash
DEPLOY_COMMIT="<full merged origin/main SHA>"
git ls-remote --heads git@github.com:Valerii-S84/quiz-arena.git main
```

Stop condition: SHA GitHub `main` не дорівнює `DEPLOY_COMMIT`, required CI не
green або PR/review threads не закриті.

## 2. Production context

```bash
set -euo pipefail

DEPLOY_COMMIT="<full merged origin/main SHA>"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE_DIR="/opt/quiz-arena-releases/${DEPLOY_COMMIT}"
COMPOSE_FILE="${RELEASE_DIR}/deploy/quiz-arena/docker-compose.prod.yml"
QUIZ_ARENA_ENV_FILE="/opt/quiz-arena/.env"
BACKEND_IMAGE="quiz-arena-backend:sha-${DEPLOY_COMMIT}"
BACKUP_DIR="/var/backups/quiz-arena/predeploy-${DEPLOY_COMMIT}-${TS}"

export DEPLOY_COMMIT RELEASE_DIR COMPOSE_FILE QUIZ_ARENA_ENV_FILE BACKEND_IMAGE BACKUP_DIR
```

Перевірити target без disclosure:

```bash
test "$(hostname)" = "ubuntu-8gb-nbg1-1"
test -d /opt/quiz-arena
test -r "${QUIZ_ARENA_ENV_FILE}"
git -C /opt/quiz-arena rev-parse HEAD
git -C /opt/quiz-arena status --short
```

`status --short` використовується тільки для класифікації path/status. Вміст
protected runtime artifacts не відкривати. Нічого не видаляти й не
перезаписувати.

## 3. Clean release checkout

```bash
test ! -e "${RELEASE_DIR}"
mkdir -p /opt/quiz-arena-releases
git clone --no-checkout git@github.com:Valerii-S84/quiz-arena.git "${RELEASE_DIR}"
git -C "${RELEASE_DIR}" checkout --detach "${DEPLOY_COMMIT}"
test "$(git -C "${RELEASE_DIR}" rev-parse HEAD)" = "${DEPLOY_COMMIT}"
test -z "$(git -C "${RELEASE_DIR}" status --porcelain)"
```

Production dirty checkout залишається untouched і є окремим protected
artifact source; deploy працює з release checkout.

## 4. Compose, volumes і edge preflight

```bash
docker network inspect quiz-arena-edge >/dev/null
docker volume inspect quiz-arena_pg_data >/dev/null
docker volume inspect quiz-arena_redis_data >/dev/null

docker compose \
  --project-directory "${RELEASE_DIR}" \
  --env-file "${QUIZ_ARENA_ENV_FILE}" \
  -f "${COMPOSE_FILE}" \
  config --quiet
```

Перевірити, що candidate compose містить тільки backend ownership:

```bash
services="$(docker compose \
  --project-directory "${RELEASE_DIR}" \
  --env-file "${QUIZ_ARENA_ENV_FILE}" \
  -f "${COMPOSE_FILE}" config --services)"

for required in postgres redis api worker beat; do
  printf '%s\n' "${services}" | grep -qx "${required}"
done
printf '%s\n' "${services}" | grep -Eq '^(frontend|caddy)$' && exit 1 || true
```

Stop condition: відсутня external network/volume, compose config invalid або
backend compose містить `frontend`/`caddy`.

## 5. Fresh PostgreSQL backup і rollback artifacts

```bash
mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

docker compose \
  --project-directory "${RELEASE_DIR}" \
  --env-file "${QUIZ_ARENA_ENV_FILE}" \
  -f "${COMPOSE_FILE}" \
  exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "${BACKUP_DIR}/quiz_arena_pg.dump"

test -s "${BACKUP_DIR}/quiz_arena_pg.dump"
docker compose \
  --project-directory "${RELEASE_DIR}" \
  --env-file "${QUIZ_ARENA_ENV_FILE}" \
  -f "${COMPOSE_FILE}" \
  exec -T postgres pg_restore --list \
  < "${BACKUP_DIR}/quiz_arena_pg.dump" >/dev/null
sha256sum "${BACKUP_DIR}/quiz_arena_pg.dump" \
  > "${BACKUP_DIR}/quiz_arena_pg.dump.sha256"
```

Зберегти exact previous runtime images без друку container env:

```bash
API_OLD_IMAGE="$(docker inspect --format '{{.Image}}' quiz-arena-api-1)"
WORKER_OLD_IMAGE="$(docker inspect --format '{{.Image}}' quiz-arena-worker-1)"
BEAT_OLD_IMAGE="$(docker inspect --format '{{.Image}}' quiz_arena_beat_prod)"
export API_OLD_IMAGE WORKER_OLD_IMAGE BEAT_OLD_IMAGE

printf 'API_OLD_IMAGE=%s\nWORKER_OLD_IMAGE=%s\nBEAT_OLD_IMAGE=%s\n' \
  "${API_OLD_IMAGE}" "${WORKER_OLD_IMAGE}" "${BEAT_OLD_IMAGE}" \
  > "${BACKUP_DIR}/previous-image-ids.txt"

docker image save \
  -o "${BACKUP_DIR}/previous-runtime-images.tar" \
  "${API_OLD_IMAGE}" "${WORKER_OLD_IMAGE}" "${BEAT_OLD_IMAGE}"
sha256sum "${BACKUP_DIR}/previous-runtime-images.tar" \
  > "${BACKUP_DIR}/previous-runtime-images.tar.sha256"
docker image load -i "${BACKUP_DIR}/previous-runtime-images.tar" >/dev/null
```

Створити rollback override:

```bash
printf 'services:\n  api:\n    image: %s\n  worker:\n    image: %s\n  beat:\n    image: %s\n' \
  "${API_OLD_IMAGE}" "${WORKER_OLD_IMAGE}" "${BEAT_OLD_IMAGE}" \
  > "${BACKUP_DIR}/rollback-images.yml"
```

## 6. Build once і migration compatibility

```bash
docker build \
  --label "org.opencontainers.image.revision=${DEPLOY_COMMIT}" \
  --tag "${BACKEND_IMAGE}" \
  "${RELEASE_DIR}"

CANDIDATE_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${BACKEND_IMAGE}")"
test -n "${CANDIDATE_IMAGE_ID}"
```

Candidate head без DB write:

```bash
CANDIDATE_HEAD="$(docker run --rm "${BACKEND_IMAGE}" \
  sh -c "alembic heads | awk '{print \$1}'")"

LIVE_CURRENT="$(docker run --rm \
  --network quiz-arena_default \
  --env-file "${QUIZ_ARENA_ENV_FILE}" \
  "${BACKEND_IMAGE}" \
  sh -c "alembic current | awk '{print \$1}'")"

test -n "${CANDIDATE_HEAD}"
test "${LIVE_CURRENT}" = "${CANDIDATE_HEAD}"
```

Якщо revisions не збігаються, не запускати `alembic upgrade`; deploy
зупиняється до окремого migration plan.

## 7. Controlled backend deploy

Recreate тільки API і worker з одного image:

```bash
docker compose \
  --project-directory "${RELEASE_DIR}" \
  --env-file "${QUIZ_ARENA_ENV_FILE}" \
  -f "${COMPOSE_FILE}" \
  up -d --no-deps --no-build api worker
```

Перевірити API edge і worker до beat:

```bash
docker network inspect quiz-arena-edge \
  --format '{{json .Containers}}' | grep -q 'quiz-arena-api-1'
docker exec infra_caddy_prod getent hosts api

for attempt in $(seq 1 30); do
  docker inspect --format '{{.State.Health.Status}}' quiz-arena-api-1 \
    | grep -qx healthy && break
  test "${attempt}" != 30
  sleep 2
done

docker exec -i quiz-arena-worker-1 python - <<'PY'
from app.workers.celery_app import celery_app

replies = celery_app.control.inspect(timeout=5).ping() or {}
raise SystemExit(0 if replies else 1)
PY
```

Замінити beat лише після green worker ping:

```bash
docker compose \
  --project-directory "${RELEASE_DIR}" \
  --env-file "${QUIZ_ARENA_ENV_FILE}" \
  -f "${COMPOSE_FILE}" \
  up -d --no-deps --no-build beat

test "$(docker ps -q \
  --filter label=com.docker.compose.project=quiz-arena \
  --filter label=com.docker.compose.service=beat | wc -l)" -eq 1
```

Перевірити один image ID для трьох runtime components:

```bash
for container in quiz-arena-api-1 quiz-arena-worker-1 quiz_arena_beat_prod; do
  test "$(docker inspect --format '{{.Image}}' "${container}")" = "${CANDIDATE_IMAGE_ID}"
  test "$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "${container}")" = "unless-stopped"
done
```

Routine backend deploy не виконує Caddy reload.

## 8. Post-deploy smoke

```bash
curl -fsS -o /dev/null https://deutchquizarena.de/health

docker exec quiz_arena_postgres_prod \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null
test "$(docker exec quiz_arena_redis_prod redis-cli ping)" = "PONG"

docker exec -i quiz-arena-worker-1 python - <<'PY'
from app.workers.celery_app import celery_app

replies = celery_app.control.inspect(timeout=5).ping() or {}
raise SystemExit(0 if replies else 1)
PY

test "$(docker ps -q \
  --filter label=com.docker.compose.project=quiz-arena \
  --filter label=com.docker.compose.service=beat | wc -l)" -eq 1

for container in quiz-arena-api-1 quiz-arena-worker-1 quiz_arena_beat_prod; do
  test "$(docker inspect --format '{{.State.Restarting}}' "${container}")" = "false"
done
```

Перевірити Telegram provider-side status усередині API container. Скрипт
використовує вже завантажений у process environment token, але не друкує token
або provider payload. Два snapshots мають підтвердити очікуваний URL, успішну
відповідь Telegram та відсутність зростання `pending_update_count`:

```bash
docker exec -i quiz-arena-api-1 python - <<'PY'
import json
import os
import time
import urllib.request

EXPECTED_URL = "https://deutchquizarena.de/webhook/telegram"


def snapshot():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not available in API environment")
    with urllib.request.urlopen(
        f"https://api.telegram.org/bot{token}/getWebhookInfo",
        timeout=12,
    ) as response:
        payload = json.load(response)
    result = payload.get("result") or {}
    return {
        "ok": payload.get("ok") is True,
        "url_matches": result.get("url") == EXPECTED_URL,
        "pending_update_count": int(result.get("pending_update_count") or 0),
        "last_error_present": "last_error_message" in result,
    }


before = snapshot()
time.sleep(30)
after = snapshot()
sanitized = {"before": before, "after": after}
print(json.dumps(sanitized, sort_keys=True))
raise SystemExit(
    0
    if before["ok"]
    and after["ok"]
    and before["url_matches"]
    and after["url_matches"]
    and after["pending_update_count"] <= before["pending_update_count"]
    else 1
)
PY
```

Окремий owner bot smoke: відправити `/start` production-боту й отримати штатну
відповідь без платежу. Якщо provider check або owner bot smoke не пройдено,
release не отримує статус `Done`.

Не читати application logs, DB rows, Redis keys, provider payloads або secret
values. У звіт записувати тільки sanitized результат наведеного check.

## 9. Rollback

Rollback trigger: health/ready failure, worker ping failure, Telegram provider
check failure, не один beat, неправильний image ID або restart loop.

```bash
BACKEND_IMAGE=rollback-placeholder docker compose \
  --project-directory "${RELEASE_DIR}" \
  --env-file "${QUIZ_ARENA_ENV_FILE}" \
  -f "${COMPOSE_FILE}" \
  -f "${BACKUP_DIR}/rollback-images.yml" \
  up -d --no-deps --no-build api worker beat

docker network inspect quiz-arena-edge \
  --format '{{json .Containers}}' | grep -q 'quiz-arena-api-1'
docker exec infra_caddy_prod getent hosts api
curl -fsS -o /dev/null https://deutchquizarena.de/health
```

Цей release не виконує schema migration, тому routine code rollback не
відновлює DB dump. Будь-який DB restore є окремою owner-approved recovery
операцією.

## 10. Заборонено

- `git reset`, `git clean`, force-push або overwrite production dirty files;
- `docker compose down`, volume deletion або prune;
- керування `frontend`, `infra-caddy`, PostgreSQL чи Redis у backend deploy;
- читання/друк `.env`, tokens, private keys, production logs, DB rows або Redis keys;
- migration, webhook, DNS або payment config changes у routine deploy.
