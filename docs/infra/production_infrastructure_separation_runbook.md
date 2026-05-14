# Production Infrastructure Separation Execution Runbook

Status: future execution runbook. Do not run these commands until a separate
maintenance window is approved.

Prepared for branch `codex/infra-separation-plan`, commit `69a7609c7352`.

## Safety Rules

- Run this only from an approved production maintenance window.
- Do not use stack-wide `docker compose down`.
- Do not use stack-wide `docker compose restart`.
- Do not prune Docker images, containers, networks, or volumes.
- Do not delete backups.
- Do not print `.env` values.
- Do not restart PostgreSQL or Redis.
- Do not run migrations.
- Do not continue after any stop condition.

## Preconditions

Required people:

- Migration operator: assigned before Phase 0.
- Verification owner: assigned before Phase 0.
- Rollback owner: assigned before Phase 0.
- Business decision owner: assigned before Phase 0.

Required state:

- Maintenance freeze is announced.
- No backend deploy is in progress.
- No frontend image switch is in progress.
- No API Quiz Bank deploy is in progress.
- No DNS, Caddy, or certificate maintenance is in progress.
- Current production Quiz Arena commit is recorded before execution.
- Current running stacks are recorded before execution.
- Fresh backups exist and were checked before cutover.

Known active runtime before this runbook:

- `/opt/quiz-arena`: active `quiz-arena` runtime.
- `/opt/api-quiz-bank`: active `api-quiz-bank` runtime.
- `/opt/infra-caddy`: not yet active before migration.
- `/opt/quiz-arena-site`: not yet active before migration.
- `quiz-arena` services: `postgres`, `redis`, `api`, `worker`, `beat`,
  `frontend`, `caddy`.
- `api-quiz-bank` services: `api-quiz-bank`, `api-quiz-bank-postgres`.

Services not to touch except where explicitly called out:

- `quiz_arena_postgres_prod`
- `quiz_arena_redis_prod`
- `quiz-arena-api-1`
- `quiz-arena-worker-1`
- `quiz_arena_beat_prod`
- `api-quiz-bank-postgres`
- unrelated `it-quiz-bot-prod` containers

Allowed planned service changes:

- Stop/remove old `quiz_arena_caddy_prod` only at the Caddy cutover step.
- Start new `infra_caddy_prod` only at the Caddy cutover step.
- Start `quiz-arena-site` frontend only at the site split step.
- Keep old `quiz-arena-frontend-1` running as a rollback runtime through the
  stability window. After the site frontend is verified, detach the old
  frontend from edge networks instead of stopping or removing it.

## Operator Shell Setup

Run on the VPS only after approval:

```bash
set -euo pipefail

export RUNBOOK_COMMIT="69a7609c7352"
export BACKUP_ROOT="/var/backups/quiz-arena"
export TS="$(date -u +%Y%m%dT%H%M%SZ)"
export BACKUP_DIR="${BACKUP_ROOT}/infra_separation_${TS}"

install -d -m 700 "${BACKUP_DIR}"
install -d -m 700 "${BACKUP_DIR}/files"
install -d -m 700 "${BACKUP_DIR}/env"
install -d -m 700 "${BACKUP_DIR}/db"
install -d -m 700 "${BACKUP_DIR}/docker"
install -d -m 700 "${BACKUP_DIR}/docker-volumes"
```

Record baseline commit and stacks:

```bash
git -C /opt/quiz-arena rev-parse HEAD > "${BACKUP_DIR}/quiz-arena.current_commit.txt"
git -C /opt/quiz-arena status --short --branch > "${BACKUP_DIR}/quiz-arena.git_status.txt"
git -C /opt/api-quiz-bank rev-parse HEAD > "${BACKUP_DIR}/api-quiz-bank.current_commit.txt"
git -C /opt/api-quiz-bank status --short --branch > "${BACKUP_DIR}/api-quiz-bank.git_status.txt"
docker compose ls --format json > "${BACKUP_DIR}/docker/compose_ls.before.json"
```

## Phase 1: Backup Commands

### File Backups

```bash
tar -C /opt -czf "${BACKUP_DIR}/files/opt_quiz-arena_tree.tgz" quiz-arena
tar -C /opt -czf "${BACKUP_DIR}/files/opt_api-quiz-bank_tree.tgz" api-quiz-bank

cp -a /opt/quiz-arena/deploy/Caddyfile \
  "${BACKUP_DIR}/files/quiz-arena.Caddyfile.before"
cp -a /opt/quiz-arena/docker-compose.prod.yml \
  "${BACKUP_DIR}/files/quiz-arena.docker-compose.prod.yml.before"
cp -a /opt/api-quiz-bank/docker-compose.api-quiz-bank.yml \
  "${BACKUP_DIR}/files/api-quiz-bank.docker-compose.api-quiz-bank.yml.before"
cp -a /opt/api-quiz-bank/docker-compose.api-quiz-bank.postgres.yml \
  "${BACKUP_DIR}/files/api-quiz-bank.docker-compose.api-quiz-bank.postgres.yml.before"
cp -a /opt/api-quiz-bank/docker-compose.api-quiz-bank.secrets.yml \
  "${BACKUP_DIR}/files/api-quiz-bank.docker-compose.api-quiz-bank.secrets.yml.before"
```

### Env Backups

Do not print values:

```bash
cp -a /opt/quiz-arena/.env "${BACKUP_DIR}/env/quiz-arena.env.before"
find /opt/quiz-arena -maxdepth 1 -type f -name '.env.*' \
  -exec cp -a {} "${BACKUP_DIR}/env/" \;

cp -a /opt/api-quiz-bank/.env "${BACKUP_DIR}/env/api-quiz-bank.env.before"
find /opt/api-quiz-bank -maxdepth 1 -type f -name '.env.*' \
  -exec cp -a {} "${BACKUP_DIR}/env/" \;

chmod -R go-rwx "${BACKUP_DIR}/env"
```

### Database Backups

Quiz Arena PostgreSQL:

```bash
docker exec quiz_arena_postgres_prod sh -lc \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --file=-' \
  > "${BACKUP_DIR}/db/quiz_arena.pg_dump"

test -s "${BACKUP_DIR}/db/quiz_arena.pg_dump"
```

API Quiz Bank PostgreSQL:

```bash
docker exec api-quiz-bank-postgres sh -lc \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --file=-' \
  > "${BACKUP_DIR}/db/api_quiz_bank.pg_dump"

test -s "${BACKUP_DIR}/db/api_quiz_bank.pg_dump"
```

### Docker Snapshot

```bash
docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' \
  > "${BACKUP_DIR}/docker/docker_ps.before.txt"
docker ps -a --format '{{json .}}' \
  > "${BACKUP_DIR}/docker/docker_ps_all.before.jsonl"
docker compose ls --format json \
  > "${BACKUP_DIR}/docker/docker_compose_ls.before.json"
docker network ls \
  > "${BACKUP_DIR}/docker/docker_network_ls.before.txt"
docker volume ls \
  > "${BACKUP_DIR}/docker/docker_volume_ls.before.txt"
docker image ls \
  > "${BACKUP_DIR}/docker/docker_image_ls.before.txt"

docker network inspect quiz-arena_default api-quiz-bank_default \
  > "${BACKUP_DIR}/docker/docker_network_inspect.current_edges.before.json"
docker volume inspect \
  quiz-arena_caddy_data \
  quiz-arena_caddy_config \
  quiz-arena_pg_data \
  quiz-arena_redis_data \
  api-quiz-bank_api-quiz-bank-postgres-data \
  > "${BACKUP_DIR}/docker/docker_volume_inspect.critical.before.json"
```

### Caddy Volume Backups

Prefer filesystem tar as root. This avoids creating temporary backup
containers:

```bash
test -d /var/lib/docker/volumes/quiz-arena_caddy_data/_data
test -d /var/lib/docker/volumes/quiz-arena_caddy_config/_data

tar -C /var/lib/docker/volumes/quiz-arena_caddy_data/_data \
  -czf "${BACKUP_DIR}/docker-volumes/quiz-arena_caddy_data.tgz" .
tar -C /var/lib/docker/volumes/quiz-arena_caddy_config/_data \
  -czf "${BACKUP_DIR}/docker-volumes/quiz-arena_caddy_config.tgz" .

test -s "${BACKUP_DIR}/docker-volumes/quiz-arena_caddy_data.tgz"
test -s "${BACKUP_DIR}/docker-volumes/quiz-arena_caddy_config.tgz"
```

Stop condition: stop if any backup command fails or any backup file is empty.

## Phase 2: Preflight Checks

### Docker Runtime

```bash
docker compose ls
docker ps
docker network ls
docker volume ls

docker inspect quiz_arena_caddy_prod \
  --format '{{.Name}} {{json .NetworkSettings.Networks}}'
docker inspect quiz-arena-api-1 \
  --format '{{.Name}} {{json .NetworkSettings.Networks}}'
docker inspect quiz-arena-frontend-1 \
  --format '{{.Name}} {{json .NetworkSettings.Networks}}'
docker inspect api-quiz-bank-pilot \
  --format '{{.Name}} {{json .NetworkSettings.Networks}}'
```

### Health And Edge Checks

```bash
curl -fsS https://deutchquizarena.de/health
curl -fsS https://deutchquizarena.46.225.181.45.sslip.io/health

curl -sS -o /tmp/api_valerchik_unauthorized.out \
  -w '%{http_code}\n' https://api.valerchik.de/health \
  | tee "${BACKUP_DIR}/docker/api_valerchik_unauthorized.before.status"
grep -qx '401' "${BACKUP_DIR}/docker/api_valerchik_unauthorized.before.status"
```

Authorized API Quiz Bank edge check without printing the key:

```bash
python3 - <<'PY'
from pathlib import Path
import urllib.error
import urllib.request

def read_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values

key = read_env("/opt/quiz-arena/.env")["API_QUIZ_BANK_PUBLIC_API_KEY"]
request = urllib.request.Request(
    "https://api.valerchik.de/health",
    headers={"X-API-Key": key},
)
try:
    with urllib.request.urlopen(request, timeout=12) as response:
        status = response.status
except urllib.error.HTTPError as exc:
    status = exc.code

print(status)
raise SystemExit(0 if status < 500 else 1)
PY
```

Telegram webhook status without printing the token:

```bash
python3 - <<'PY'
from pathlib import Path
import json
import urllib.request

def read_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values

token = read_env("/opt/quiz-arena/.env")["TELEGRAM_BOT_TOKEN"]
with urllib.request.urlopen(
    f"https://api.telegram.org/bot{token}/getWebhookInfo",
    timeout=12,
) as response:
    payload = json.load(response)

result = payload.get("result") or {}
sanitized = {
    "ok": payload.get("ok"),
    "url": result.get("url"),
    "pending_update_count": result.get("pending_update_count"),
    "last_error_date": result.get("last_error_date"),
    "last_error_message_present": "last_error_message" in result,
    "max_connections": result.get("max_connections"),
    "allowed_updates": result.get("allowed_updates"),
}
print(json.dumps(sanitized, sort_keys=True))
raise SystemExit(
    0
    if payload.get("ok")
    and result.get("url") == "https://deutchquizarena.de/webhook/telegram"
    else 1
)
PY
```

### Database, Redis, And Celery

```bash
docker exec quiz_arena_postgres_prod sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from public.users;"' \
  | tee "${BACKUP_DIR}/docker/quiz_arena_users_count.before.txt"

for queue in q_high q_normal q_low celery; do
  printf '%s=' "${queue}"
  docker exec quiz_arena_redis_prod redis-cli LLEN "${queue}"
done | tee "${BACKUP_DIR}/docker/redis_queue_lengths.before.txt"

docker exec -i quiz-arena-worker-1 python - <<'PY' \
  | tee "${BACKUP_DIR}/docker/celery_counts.before.json"
import json
from app.workers.celery_app import celery_app

inspect = celery_app.control.inspect(timeout=5)
summary = {}
for name, method in {
    "active": inspect.active,
    "reserved": inspect.reserved,
    "scheduled": inspect.scheduled,
}.items():
    data = method() or {}
    summary[name] = {worker: len(tasks or []) for worker, tasks in data.items()}
print(json.dumps(summary, sort_keys=True))
PY
```

Stop condition: stop if health is not `200`, unauthorized API Quiz Bank check is
not `401`, authorized API Quiz Bank check is `502` or any `5xx`, Telegram URL is
wrong, pending updates are growing, DB/Redis/Celery checks fail, or Docker state
does not match the expected stacks.

## Phase 3: Create External Networks

Create networks only if missing:

```bash
for network in quiz-arena-edge quiz-arena-site-edge api-quiz-bank-edge; do
  if docker network inspect "${network}" >/dev/null 2>&1; then
    echo "exists ${network}"
  else
    docker network create "${network}"
  fi
done
```

Attach currently running upstreams without restarting containers:

```bash
docker network inspect quiz-arena-edge \
  --format '{{json .Containers}}' | grep -q 'quiz-arena-api-1' \
  || docker network connect --alias api quiz-arena-edge quiz-arena-api-1

docker network inspect quiz-arena-edge \
  --format '{{json .Containers}}' | grep -q 'quiz-arena-frontend-1' \
  || docker network connect quiz-arena-edge quiz-arena-frontend-1

docker network inspect quiz-arena-site-edge \
  --format '{{json .Containers}}' | grep -q 'quiz-arena-frontend-1' \
  || docker network connect --alias site-frontend quiz-arena-site-edge quiz-arena-frontend-1

docker network inspect api-quiz-bank-edge \
  --format '{{json .Containers}}' | grep -q 'api-quiz-bank-pilot' \
  || docker network connect --alias api-quiz-bank api-quiz-bank-edge api-quiz-bank-pilot
```

Verify network membership:

```bash
docker network inspect quiz-arena-edge \
  --format '{{range $id, $c := .Containers}}{{println $c.Name}}{{end}}'
docker network inspect quiz-arena-site-edge \
  --format '{{range $id, $c := .Containers}}{{println $c.Name}}{{end}}'
docker network inspect api-quiz-bank-edge \
  --format '{{range $id, $c := .Containers}}{{println $c.Name}}{{end}}'
```

Verify upstream DNS from the future Caddy networks:

```bash
docker run --rm --network quiz-arena-edge alpine:3.20 \
  sh -lc 'getent hosts api'
docker run --rm --network quiz-arena-site-edge alpine:3.20 \
  sh -lc 'getent hosts site-frontend'
docker run --rm --network api-quiz-bank-edge alpine:3.20 \
  sh -lc 'getent hosts api-quiz-bank'
```

Rollback for Phase 3:

```bash
docker network disconnect quiz-arena-edge quiz-arena-api-1 || true
docker network disconnect quiz-arena-edge quiz-arena-frontend-1 || true
docker network disconnect quiz-arena-site-edge quiz-arena-frontend-1 || true
docker network disconnect api-quiz-bank-edge api-quiz-bank-pilot || true

for network in quiz-arena-edge quiz-arena-site-edge api-quiz-bank-edge; do
  containers="$(docker network inspect "${network}" \
    --format '{{len .Containers}}' 2>/dev/null || echo 1)"
  if [ "${containers}" = "0" ]; then
    docker network rm "${network}"
  else
    echo "not removing ${network}; containers still attached"
  fi
done
```

Rollback verification:

```bash
curl -fsS https://deutchquizarena.de/health
```

## Phase 4: Prepare `/opt/infra-caddy`

Fetch the reviewed branch into the existing repo without changing the working
tree:

```bash
git -C /opt/quiz-arena fetch origin codex/infra-separation-plan
git -C /opt/quiz-arena cat-file -e "${RUNBOOK_COMMIT}^{commit}"
```

Create the infra directory and copy reviewed files from the pinned commit:

```bash
install -d -m 755 /opt/infra-caddy

git -C /opt/quiz-arena show \
  "${RUNBOOK_COMMIT}:deploy/infra-caddy/docker-compose.yml" \
  > /opt/infra-caddy/docker-compose.yml

git -C /opt/quiz-arena show \
  "${RUNBOOK_COMMIT}:deploy/infra-caddy/Caddyfile" \
  > /opt/infra-caddy/Caddyfile
```

Create `.env.caddy` without printing values:

```bash
python3 - <<'PY'
from pathlib import Path

source = Path("/opt/quiz-arena/.env")
target = Path("/opt/infra-caddy/.env.caddy")
keys = [
    "API_QUIZ_BANK_PUBLIC_API_KEY",
    "CADDY_EMAIL",
    "DOMAIN",
]

values: dict[str, str] = {}
for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("export "):
        line = line[len("export "):].lstrip()
    if "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip()

missing = [key for key in keys if key not in values]
if missing:
    raise SystemExit(f"missing keys for .env.caddy: {', '.join(missing)}")

target.write_text(
    "".join(f"{key}={values[key]}\n" for key in keys),
    encoding="utf-8",
)
target.chmod(0o600)
PY
```

Validate compose and Caddy config without starting public Caddy:

```bash
cd /opt/infra-caddy
docker compose --env-file .env.caddy -f docker-compose.yml config --quiet

docker run --rm \
  --env-file /opt/infra-caddy/.env.caddy \
  -v /opt/infra-caddy/Caddyfile:/etc/caddy/Caddyfile:ro \
  caddy:2.8 caddy validate --config /etc/caddy/Caddyfile
```

Rollback for Phase 4:

```bash
mv /opt/infra-caddy "/opt/infra-caddy.rollback_${TS}" || true
curl -fsS https://deutchquizarena.de/health
```

## Phase 5: Caddy Cutover

Final pre-cutover checks:

```bash
docker ps --filter name=quiz_arena_caddy_prod
curl -fsS https://deutchquizarena.de/health
```

Stop only the old Caddy service:

```bash
cd /opt/quiz-arena
docker compose -f docker-compose.prod.yml --env-file .env stop caddy
docker compose -f docker-compose.prod.yml --env-file .env rm -f caddy
```

Start only the new infra Caddy:

```bash
cd /opt/infra-caddy
docker compose --env-file .env.caddy -f docker-compose.yml up -d caddy
docker compose --env-file .env.caddy -f docker-compose.yml ps
```

Immediate route verification:

```bash
curl -fsS https://deutchquizarena.de/health
curl -fsS https://deutchquizarena.46.225.181.45.sslip.io/health
curl -sS -o /tmp/api_ready.out -w '%{http_code}\n' \
  https://deutchquizarena.de/api/ready | grep -qx '404'
curl -sS -o /tmp/api_valerchik_unauthorized.out -w '%{http_code}\n' \
  https://api.valerchik.de/health | grep -qx '401'
```

Authorized API Quiz Bank check:

```bash
python3 - <<'PY'
from pathlib import Path
import urllib.error
import urllib.request

def read_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values

key = read_env("/opt/infra-caddy/.env.caddy")["API_QUIZ_BANK_PUBLIC_API_KEY"]
request = urllib.request.Request(
    "https://api.valerchik.de/health",
    headers={"X-API-Key": key},
)
try:
    with urllib.request.urlopen(request, timeout=12) as response:
        status = response.status
except urllib.error.HTTPError as exc:
    status = exc.code
print(status)
raise SystemExit(0 if status < 500 else 1)
PY
```

Rollback for Phase 5:

```bash
cd /opt/infra-caddy
docker compose --env-file .env.caddy -f docker-compose.yml stop caddy || true
docker compose --env-file .env.caddy -f docker-compose.yml rm -f caddy || true

cd /opt/quiz-arena
docker compose -f docker-compose.prod.yml --env-file .env up -d caddy
docker compose -f docker-compose.prod.yml --env-file .env ps caddy

curl -fsS https://deutchquizarena.de/health
curl -sS -o /tmp/api_valerchik_unauthorized.rollback.out -w '%{http_code}\n' \
  https://api.valerchik.de/health | grep -qx '401'
```

Telegram rollback verification:

```bash
python3 - <<'PY'
from pathlib import Path
import json
import urllib.request

def read_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values

token = read_env("/opt/quiz-arena/.env")["TELEGRAM_BOT_TOKEN"]
with urllib.request.urlopen(
    f"https://api.telegram.org/bot{token}/getWebhookInfo",
    timeout=12,
) as response:
    payload = json.load(response)
result = payload.get("result") or {}
print(json.dumps({
    "ok": payload.get("ok"),
    "url": result.get("url"),
    "pending_update_count": result.get("pending_update_count"),
}, sort_keys=True))
PY
```

Stop condition: rollback immediately if health is not `200`, public
`/api/ready` is not `404`, unauthorized API Quiz Bank is not `401`, authorized
API Quiz Bank is `502` or any `5xx`, Caddy logs show upstream resolution errors,
or Telegram pending updates start increasing.

## Phase 6: Post-Caddy Verification

Run the full verification checklist from this runbook. Also inspect logs:

```bash
cd /opt/infra-caddy
docker compose --env-file .env.caddy -f docker-compose.yml logs --since 15m caddy

cd /opt/quiz-arena
docker compose -f docker-compose.prod.yml --env-file .env logs --since 15m api
docker compose -f docker-compose.prod.yml --env-file .env logs --since 15m worker
```

Rollback for Phase 6: use Phase 5 rollback.

## Phase 7: Prepare `/opt/quiz-arena-site`

Create site directory and copy reviewed compose:

```bash
install -d -m 755 /opt/quiz-arena-site

git -C /opt/quiz-arena show \
  "${RUNBOOK_COMMIT}:deploy/quiz-arena-site/docker-compose.prod.yml" \
  > /opt/quiz-arena-site/docker-compose.prod.yml
```

Create `.env.site` without printing values:

```bash
python3 - <<'PY'
from pathlib import Path

source = Path("/opt/quiz-arena/.env")
target = Path("/opt/quiz-arena-site/.env.site")
keys = [
    "FRONTEND_IMAGE",
    "QUIZ_BANK_API_BASE_URL",
    "QUIZ_BANK_CONSUMER_API_KEY",
    "QUIZ_BANK_CONSUMER_ID",
    "QUIZ_BANK_EDGE_API_KEY",
]

values: dict[str, str] = {}
for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip()

missing = [key for key in keys if key not in values]
if missing:
    raise SystemExit(f"missing keys for .env.site: {', '.join(missing)}")

if "FRONTEND_API_INTERNAL_URL" not in values:
    values["FRONTEND_API_INTERNAL_URL"] = "http://api:8000"

ordered = keys + ["FRONTEND_API_INTERNAL_URL"]
target.write_text(
    "".join(f"{key}={values[key]}\n" for key in ordered),
    encoding="utf-8",
)
target.chmod(0o600)
PY
```

Validate site compose:

```bash
cd /opt/quiz-arena-site
docker compose --env-file .env.site -f docker-compose.prod.yml config --quiet
```

Rollback for Phase 7:

```bash
mv /opt/quiz-arena-site "/opt/quiz-arena-site.rollback_${TS}" || true
curl -fsS https://deutchquizarena.de/health
```

## Phase 8: Move Frontend Runtime To `quiz-arena-site`

Start the new site frontend:

```bash
cd /opt/quiz-arena-site
docker compose --env-file .env.site -f docker-compose.prod.yml up -d frontend
docker compose --env-file .env.site -f docker-compose.prod.yml ps
```

Keep Caddy pinned to the old frontend while the new site frontend starts:

```bash
cd /opt/infra-caddy
cp -a Caddyfile "${BACKUP_DIR}/files/infra-caddy.Caddyfile.pre_site_route_switch"
python3 - <<'PY'
from pathlib import Path

path = Path("/opt/infra-caddy/Caddyfile")
text = path.read_text(encoding="utf-8")
for old in ("site-frontend:3000", "frontend:3000"):
    text = text.replace(old, "quiz-arena-frontend-1:3000")
path.write_text(text, encoding="utf-8")
PY
docker compose --env-file .env.caddy -f docker-compose.yml exec -T caddy \
  caddy reload --config /etc/caddy/Caddyfile
```

Readiness-gate the new frontend internally before any public route switch:

```bash
docker run --rm --network quiz-arena-edge alpine:3.20 \
  sh -lc 'wget -q -O /tmp/site_frontend.html --timeout=5 http://quiz-arena-site-frontend-1:3000/ && test -s /tmp/site_frontend.html'
docker run --rm --network quiz-arena-site-edge alpine:3.20 \
  sh -lc 'wget -q -O /tmp/site_frontend.html --timeout=5 http://quiz-arena-site-frontend-1:3000/ && test -s /tmp/site_frontend.html'
```

Move the stable `site-frontend` alias to the new site container only after the
internal readiness checks pass:

```bash
docker network disconnect quiz-arena-site-edge quiz-arena-frontend-1 || true
docker network inspect quiz-arena-site-edge \
  --format '{{json .Containers}}' | grep -q 'quiz-arena-site-frontend-1' \
  || docker network connect --alias site-frontend quiz-arena-site-edge quiz-arena-site-frontend-1
docker exec infra_caddy_prod getent hosts site-frontend
docker run --rm --network quiz-arena-site-edge alpine:3.20 \
  sh -lc 'wget -q -O /tmp/site_frontend.html --timeout=5 http://site-frontend:3000/ && test -s /tmp/site_frontend.html'
```

Switch Caddy to the stable site frontend upstream:

```bash
cd /opt/infra-caddy
python3 - <<'PY'
from pathlib import Path

path = Path("/opt/infra-caddy/Caddyfile")
allowed = {
    "frontend:3000",
    "quiz-arena-frontend-1:3000",
    "quiz-arena-site-frontend-1:3000",
    "site-frontend:3000",
}
lines = []
for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
    newline = "\n" if line.endswith("\n") else ""
    raw = line[:-1] if newline else line
    leading = raw[: len(raw) - len(raw.lstrip())]
    parts = raw.split()
    if len(parts) == 2 and parts[0] == "reverse_proxy" and parts[1] in allowed:
        line = f"{leading}reverse_proxy site-frontend:3000{newline}"
    lines.append(line)
path.write_text("".join(lines), encoding="utf-8")
PY
docker run --rm \
  --env-file /opt/infra-caddy/.env.caddy \
  -v /opt/infra-caddy/Caddyfile:/etc/caddy/Caddyfile:ro \
  caddy:2.8 caddy validate --config /etc/caddy/Caddyfile
docker compose --env-file .env.caddy -f docker-compose.yml exec -T caddy \
  caddy reload --config /etc/caddy/Caddyfile
```

Verify new frontend container and edge route:

```bash
docker ps --filter label=com.docker.compose.project=quiz-arena-site
curl -fsS https://deutchquizarena.de/ >/tmp/frontend_after_site_split.html
test -s /tmp/frontend_after_site_split.html
curl -sS -o /tmp/quiz_teaser_after_site_split.out -w '%{http_code}\n' \
  https://deutchquizarena.de/api/quiz-teaser/ \
  | tee "${BACKUP_DIR}/docker/quiz_teaser_after_site_split.status"
if grep -Eq '^5[0-9][0-9]$' "${BACKUP_DIR}/docker/quiz_teaser_after_site_split.status"; then
  exit 1
fi
```

If the route is healthy and Caddy logs are clean, detach the old frontend from
edge networks. Keep the old frontend container available for rollback through
the 24-48 hour stability window; do not stop or remove it during this phase:

```bash
docker network disconnect quiz-arena-edge quiz-arena-frontend-1 || true
docker network disconnect quiz-arena-site-edge quiz-arena-frontend-1 || true
```

Copy backend-only target compose into `/opt/quiz-arena` after old Caddy and old
frontend public routing are no longer active:

```bash
cp -a /opt/quiz-arena/docker-compose.prod.yml \
  "${BACKUP_DIR}/files/quiz-arena.docker-compose.prod.yml.pre_backend_only_switch"

git -C /opt/quiz-arena show \
  "${RUNBOOK_COMMIT}:deploy/quiz-arena/docker-compose.prod.yml" \
  > /opt/quiz-arena/docker-compose.prod.yml

cd /opt/quiz-arena
docker compose --env-file .env -f docker-compose.prod.yml config --quiet
```

Rollback for Phase 8:

```bash
docker network inspect quiz-arena-edge \
  --format '{{json .Containers}}' | grep -q 'quiz-arena-frontend-1' \
  || docker network connect quiz-arena-edge quiz-arena-frontend-1

cd /opt/infra-caddy
cp -a Caddyfile "${BACKUP_DIR}/files/infra-caddy.Caddyfile.pre_phase8_rollback"
python3 - <<'PY'
from pathlib import Path

path = Path("/opt/infra-caddy/Caddyfile")
allowed = {
    "frontend:3000",
    "site-frontend:3000",
    "quiz-arena-site-frontend-1:3000",
    "quiz-arena-frontend-1:3000",
}
lines = []
for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
    newline = "\n" if line.endswith("\n") else ""
    raw = line[:-1] if newline else line
    leading = raw[: len(raw) - len(raw.lstrip())]
    parts = raw.split()
    if len(parts) == 2 and parts[0] == "reverse_proxy" and parts[1] in allowed:
        line = f"{leading}reverse_proxy quiz-arena-frontend-1:3000{newline}"
    lines.append(line)
path.write_text("".join(lines), encoding="utf-8")
PY
docker run --rm \
  --env-file /opt/infra-caddy/.env.caddy \
  -v /opt/infra-caddy/Caddyfile:/etc/caddy/Caddyfile:ro \
  caddy:2.8 caddy validate --config /etc/caddy/Caddyfile
docker compose --env-file .env.caddy -f docker-compose.yml exec -T caddy \
  caddy reload --config /etc/caddy/Caddyfile

curl -fsS https://deutchquizarena.de/ >/tmp/frontend_rollback.html
test -s /tmp/frontend_rollback.html
curl -fsS https://deutchquizarena.de/health
curl -sS -o /tmp/quiz_teaser_rollback.out -w '%{http_code}\n' \
  https://deutchquizarena.de/api/quiz-teaser/ \
  | grep -Evq '^5[0-9][0-9]$'
curl -sS -o /tmp/api_ready_rollback.out -w '%{http_code}\n' \
  https://deutchquizarena.de/api/ready \
  | grep -qx '404'
```

Stop condition: rollback if frontend does not load, `/api/quiz-teaser/*` gives
`502`, Caddy logs show `site-frontend` resolution errors, or API logs show new
errors after the split.

Post-Phase 8 expected production state:

- Active frontend: `quiz-arena-site-frontend-1`.
- Public Caddy frontend upstream: `site-frontend:3000`.
- Old frontend rollback runtime: `quiz-arena-frontend-1` remains running but is
  detached from `quiz-arena-edge` and `quiz-arena-site-edge`; it remains on
  `quiz-arena_default` only.
- If rollback to the old frontend is needed after edge detach, reconnect
  `quiz-arena-frontend-1` to `quiz-arena-edge`, switch Caddy frontend upstreams
  to `quiz-arena-frontend-1:3000`, reload Caddy, then verify frontend,
  `/api/quiz-teaser/*`, `/health`, public `/api/ready`, Telegram webhook, and
  Caddy logs.
- Phase 9 env split is not part of Phase 8 and must not run without a separate
  explicit GO.

## Phase 9: Split Quiz Arena Env File

This phase changes env ownership only after Caddy and frontend are already
stable. It must not restart PostgreSQL or Redis.

Create `.env.quiz-arena` from the existing file without printing values:

```bash
python3 - <<'PY'
from pathlib import Path

source = Path("/opt/quiz-arena/.env")
target = Path("/opt/quiz-arena/.env.quiz-arena")
keys = [
    "ADMIN_2FA_REQUIRED",
    "ADMIN_ACCESS_TOKEN_TTL_MINUTES",
    "ADMIN_EMAIL",
    "ADMIN_FRONTEND_ORIGIN",
    "ADMIN_JWT_SECRET",
    "ADMIN_LOGIN_RATE_LIMIT_ATTEMPTS",
    "ADMIN_LOGIN_RATE_LIMIT_WINDOW_MINUTES",
    "ADMIN_PASSWORD_HASH",
    "ADMIN_PASSWORD_PLAIN",
    "ADMIN_REFRESH_SECRET",
    "ADMIN_REFRESH_TOKEN_TTL_DAYS",
    "ADMIN_TOTP_ISSUER",
    "ADMIN_TOTP_SECRET",
    "API_WORKERS",
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "BONUS_CHANNEL_ID",
    "BONUS_CHECK_BOT_TOKEN",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "CELERY_WORKER_CONCURRENCY",
    "DATABASE_URL",
    "ENABLE_OPENAPI_DOCS",
    "FRIEND_CHALLENGE_DEADLINE_BATCH_SIZE",
    "FRIEND_CHALLENGE_DEADLINE_SCAN_INTERVAL_SECONDS",
    "FRIEND_CHALLENGE_LAST_CHANCE_SECONDS",
    "FRIEND_CHALLENGE_TTL_SECONDS",
    "INTERNAL_API_ALLOWLIST",
    "INTERNAL_API_TOKEN",
    "INTERNAL_API_TRUSTED_PROXIES",
    "LOG_LEVEL",
    "OFFERS_ALERT_MAX_DISMISS_RATE",
    "OFFERS_ALERT_MAX_IMPRESSIONS_PER_USER",
    "OFFERS_ALERT_MIN_CONVERSION_RATE",
    "OFFERS_ALERT_MIN_IMPRESSIONS",
    "OFFERS_ALERT_WINDOW_HOURS",
    "OPS_ALERT_ESCALATION_POLICY_JSON",
    "OPS_ALERT_PAGERDUTY_EVENTS_URL",
    "OPS_ALERT_PAGERDUTY_ROUTING_KEY",
    "OPS_ALERT_SLACK_WEBHOOK_URL",
    "OPS_ALERT_WEBHOOK_URL",
    "POSTGRES_DB",
    "POSTGRES_PASSWORD",
    "POSTGRES_USER",
    "PROMO_ENCRYPTION_KEY",
    "PROMO_SECRET_PEPPER",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED",
    "QUIZ_QUESTION_POOL_CACHE_TTL_SECONDS",
    "REDIS_URL",
    "REFERRALS_ALERT_MAX_FRAUD_REJECTED_RATE",
    "REFERRALS_ALERT_MAX_REFERRER_REJECTED_FRAUD",
    "REFERRALS_ALERT_MAX_REJECTED_FRAUD_TOTAL",
    "REFERRALS_ALERT_MIN_STARTED",
    "REFERRALS_ALERT_WINDOW_HOURS",
    "RETENTION_ANALYTICS_EVENTS_DAYS",
    "RETENTION_CLEANUP_BATCH_SIZE",
    "RETENTION_CLEANUP_BATCH_SLEEP_MAX_MS",
    "RETENTION_CLEANUP_BATCH_SLEEP_MIN_MS",
    "RETENTION_CLEANUP_MAX_BATCHES_PER_TABLE",
    "RETENTION_CLEANUP_MAX_RUNTIME_SECONDS",
    "RETENTION_CLEANUP_SCHEDULE_HOUR_BERLIN",
    "RETENTION_CLEANUP_SCHEDULE_MINUTE_BERLIN",
    "RETENTION_CLEANUP_SCHEDULE_SECONDS",
    "RETENTION_OUTBOX_EVENTS_DAYS",
    "RETENTION_PROCESSED_UPDATES_DAYS",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_HOME_HEADER_FILE_ID",
    "TELEGRAM_UPDATES_ALERT_WINDOW_MINUTES",
    "TELEGRAM_UPDATES_FAILED_FINAL_SPIKE_THRESHOLD",
    "TELEGRAM_UPDATES_OBSERVABILITY_TOP_STUCK_LIMIT",
    "TELEGRAM_UPDATES_RETRY_SPIKE_THRESHOLD",
    "TELEGRAM_UPDATES_STUCK_ALERT_MIN_MINUTES",
    "TELEGRAM_UPDATE_PROCESSING_TTL_SECONDS",
    "TELEGRAM_UPDATE_TASK_MAX_RETRIES",
    "TELEGRAM_UPDATE_TASK_RETRY_BACKOFF_MAX_SECONDS",
    "TELEGRAM_WEBHOOK_ENQUEUE_TIMEOUT_MS",
    "TELEGRAM_WEBHOOK_SECRET",
]

values: dict[str, str] = {}
for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip()

missing = [key for key in keys if key not in values]
if missing:
    raise SystemExit(f"missing keys for .env.quiz-arena: {', '.join(missing)}")

target.write_text(
    "".join(f"{key}={values[key]}\n" for key in keys),
    encoding="utf-8",
)
target.chmod(0o600)
PY
```

Validate backend compose against split env:

```bash
cd /opt/quiz-arena
docker compose --env-file .env.quiz-arena -f docker-compose.prod.yml config --quiet
```

Do not restart backend services in this phase unless a separate approved
service-specific env reload is scheduled.

If an approved service-specific env reload is scheduled, restart only the
backend services that need the split env. The `api` service must remain
reachable from Caddy through `api:8000` on `quiz-arena-edge`; verify or
reconnect that edge alias before running public route checks.

Restart and readiness-gate `api`:

```bash
cd /opt/quiz-arena
docker compose --env-file .env.quiz-arena -f docker-compose.prod.yml up -d \
  --no-deps --no-build api

docker network inspect quiz-arena-edge \
  --format '{{json .Containers}}' | grep -q 'quiz-arena-api-1' \
  || docker network connect --alias api quiz-arena-edge quiz-arena-api-1

docker exec infra_caddy_prod getent hosts api
docker exec infra_caddy_prod caddy reload --config /etc/caddy/Caddyfile

for attempt in $(seq 1 30); do
  if docker run --rm --network quiz-arena-edge alpine:3.20 \
    sh -lc 'wget -q -O /tmp/api_ready.out --timeout=3 http://api:8000/ready && test -s /tmp/api_ready.out'
  then
    break
  fi
  if [ "${attempt}" = "30" ]; then
    echo "api did not become ready on quiz-arena-edge" >&2
    exit 1
  fi
  sleep 2
done

curl -fsS https://deutchquizarena.de/health
curl -sS -o /tmp/api_ready_after_phase9.out -w '%{http_code}\n' \
  https://deutchquizarena.de/api/ready \
  | grep -qx '404'
```

Restart worker only after `api` is healthy through Caddy. Do not call the
final public `/health` check until Celery responds: `/health` includes a
Celery worker ping and can return `503` while the worker is still booting.

```bash
cd /opt/quiz-arena
docker compose --env-file .env.quiz-arena -f docker-compose.prod.yml up -d \
  --no-deps --no-build worker

for attempt in $(seq 1 30); do
  if docker exec -i quiz-arena-worker-1 python - <<'PY'
from app.workers.celery_app import celery_app

replies = celery_app.control.inspect(timeout=5).ping() or {}
raise SystemExit(0 if replies else 1)
PY
  then
    break
  fi
  if [ "${attempt}" = "30" ]; then
    echo "celery worker did not respond to ping" >&2
    exit 1
  fi
  sleep 2
done

docker compose --env-file .env.quiz-arena -f docker-compose.prod.yml up -d \
  --no-deps --no-build beat
```

Rollback for Phase 9:

```bash
rm -f /opt/quiz-arena/.env.quiz-arena
cp -a "${BACKUP_DIR}/env/quiz-arena.env.before" /opt/quiz-arena/.env
cp -a "${BACKUP_DIR}/files/quiz-arena.docker-compose.prod.yml.before" \
  /opt/quiz-arena/docker-compose.prod.yml

cd /opt/quiz-arena
docker compose -f docker-compose.prod.yml --env-file .env up -d \
  --no-deps --no-build api worker beat

docker network inspect quiz-arena-edge \
  --format '{{json .Containers}}' | grep -q 'quiz-arena-api-1' \
  || docker network connect --alias api quiz-arena-edge quiz-arena-api-1
docker exec infra_caddy_prod getent hosts api
docker exec infra_caddy_prod caddy reload --config /etc/caddy/Caddyfile

curl -fsS https://deutchquizarena.de/health
curl -fsS https://deutchquizarena.de/ >/tmp/frontend_phase9_rollback.html
test -s /tmp/frontend_phase9_rollback.html
curl -sS -o /tmp/api_valerchik_unauthorized_phase9_rollback.out \
  -w '%{http_code}\n' https://api.valerchik.de/health \
  | grep -qx '401'
```

## Phase 10: Final Verification Checklist

Run all checks and save outputs:

```bash
curl -fsS https://deutchquizarena.de/health \
  | tee "${BACKUP_DIR}/docker/health.final.json"
curl -fsS https://deutchquizarena.46.225.181.45.sslip.io/health \
  | tee "${BACKUP_DIR}/docker/sslip_health.final.json"

curl -sS -o /tmp/api_ready.final.out -w '%{http_code}\n' \
  https://deutchquizarena.de/api/ready \
  | tee "${BACKUP_DIR}/docker/api_ready.final.status"
grep -qx '404' "${BACKUP_DIR}/docker/api_ready.final.status"

curl -fsS https://deutchquizarena.de/api/health >/tmp/api_route.final.out \
  || true
curl -fsS https://deutchquizarena.de/ >/tmp/frontend.final.html
test -s /tmp/frontend.final.html
curl -sS -o /tmp/quiz_teaser.final.out -w '%{http_code}\n' \
  https://deutchquizarena.de/api/quiz-teaser/ \
  | tee "${BACKUP_DIR}/docker/quiz_teaser.final.status"
if grep -Eq '^5[0-9][0-9]$' "${BACKUP_DIR}/docker/quiz_teaser.final.status"; then
  exit 1
fi

curl -sS -o /tmp/api_valerchik_unauthorized.final.out -w '%{http_code}\n' \
  https://api.valerchik.de/health \
  | tee "${BACKUP_DIR}/docker/api_valerchik_unauthorized.final.status"
grep -qx '401' "${BACKUP_DIR}/docker/api_valerchik_unauthorized.final.status"
```

Authorized API Quiz Bank final check:

```bash
python3 - <<'PY'
from pathlib import Path
import urllib.error
import urllib.request

values = {}
for raw in Path("/opt/infra-caddy/.env.caddy").read_text(encoding="utf-8").splitlines():
    if "=" in raw and not raw.strip().startswith("#"):
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")

request = urllib.request.Request(
    "https://api.valerchik.de/health",
    headers={"X-API-Key": values["API_QUIZ_BANK_PUBLIC_API_KEY"]},
)
try:
    with urllib.request.urlopen(request, timeout=12) as response:
        status = response.status
except urllib.error.HTTPError as exc:
    status = exc.code
print(status)
raise SystemExit(0 if status < 500 else 1)
PY
```

Telegram final check:

```bash
python3 - <<'PY'
from pathlib import Path
import json
import urllib.request

values = {}
for raw in Path("/opt/quiz-arena/.env").read_text(encoding="utf-8").splitlines():
    if "=" in raw and not raw.strip().startswith("#"):
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")

with urllib.request.urlopen(
    f"https://api.telegram.org/bot{values['TELEGRAM_BOT_TOKEN']}/getWebhookInfo",
    timeout=12,
) as response:
    payload = json.load(response)
result = payload.get("result") or {}
sanitized = {
    "ok": payload.get("ok"),
    "url": result.get("url"),
    "pending_update_count": result.get("pending_update_count"),
    "last_error_date": result.get("last_error_date"),
    "last_error_message_present": "last_error_message" in result,
}
print(json.dumps(sanitized, sort_keys=True))
raise SystemExit(
    0
    if payload.get("ok")
    and result.get("url") == "https://deutchquizarena.de/webhook/telegram"
    else 1
)
PY
```

Database and queue final checks:

```bash
docker exec quiz_arena_postgres_prod sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from public.users;"' \
  | tee "${BACKUP_DIR}/docker/quiz_arena_users_count.final.txt"

for queue in q_high q_normal q_low celery; do
  printf '%s=' "${queue}"
  docker exec quiz_arena_redis_prod redis-cli LLEN "${queue}"
done | tee "${BACKUP_DIR}/docker/redis_queue_lengths.final.txt"

docker exec -i quiz-arena-worker-1 python - <<'PY' \
  | tee "${BACKUP_DIR}/docker/celery_counts.final.json"
import json
from app.workers.celery_app import celery_app

inspect = celery_app.control.inspect(timeout=5)
summary = {}
for name, method in {
    "active": inspect.active,
    "reserved": inspect.reserved,
    "scheduled": inspect.scheduled,
}.items():
    data = method() or {}
    summary[name] = {worker: len(tasks or []) for worker, tasks in data.items()}
print(json.dumps(summary, sort_keys=True))
PY
```

Logs:

```bash
cd /opt/infra-caddy
docker compose --env-file .env.caddy -f docker-compose.yml logs --since 30m caddy \
  | tee "${BACKUP_DIR}/docker/infra_caddy.final.logs"

cd /opt/quiz-arena
docker compose --env-file .env -f docker-compose.prod.yml logs --since 30m api \
  | tee "${BACKUP_DIR}/docker/quiz_arena_api.final.logs"
docker compose --env-file .env -f docker-compose.prod.yml logs --since 30m worker \
  | tee "${BACKUP_DIR}/docker/quiz_arena_worker.final.logs"
```

## Stop Conditions

Stop the migration and roll back to the last known good phase if any condition
is true:

- Any backup command fails.
- Any required backup file is missing or empty.
- Caddy cannot resolve `api`, `site-frontend`, or `api-quiz-bank`.
- Caddy logs show repeated upstream resolution errors.
- `https://deutchquizarena.de/health` is not `200`.
- SSLIP health route is not `200`.
- Telegram webhook URL is wrong.
- Telegram `pending_update_count` increases after cutover.
- Public `/api/ready` does not return `404`.
- `/api/*` returns unexpected `5xx`.
- `/api/quiz-teaser/*` returns `502`.
- Frontend does not open.
- API Quiz Bank unauthorized route is not `401`.
- API Quiz Bank authorized route is `502` or any `5xx`.
- DB user count query fails.
- Redis queue checks fail.
- Celery inspect fails.
- Docker networks or volumes are in an unclear state.
- PostgreSQL or Redis show errors or unexpected restarts.

## Post-Migration Stability Window

Duration: 24-48 hours.

Rules:

- Do not delete old compose files.
- Do not delete old Caddyfile backups.
- Do not delete `.env` backups.
- Do not delete Docker volumes.
- Do not run Docker prune.
- Do not remove old Docker networks unless separately approved.
- Do not clean images or containers unless separately approved.
- Monitor only.

Monitor:

- Caddy logs.
- Quiz Arena API logs.
- Quiz Arena worker logs.
- API Quiz Bank logs.
- Telegram webhook status.
- `pending_update_count`.
- API Quiz Bank unauthorized and authorized edge checks.
- Redis queue lengths.
- Celery active/reserved/scheduled counts.
- DB users count trend.

Cleanup is a separate task after the stability window and explicit approval.
