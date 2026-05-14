# Production Infrastructure Separation Plan

Status: draft plan only. Do not execute this document without a separate
approved migration window.

## Guardrails

- Do not run `docker compose up`, `down`, `restart`, or `rm` during planning.
- Do not edit live VPS `.env` files during planning.
- Do not edit the live VPS Caddyfile during planning.
- Do not detach Docker networks during planning.
- Do not move Docker volumes during planning.
- Do not deploy, run migrations, clean Docker state, or print secrets.

## Current State

Confirmed by live read-only inventory:

- `/opt/quiz-arena` exists and owns the active Quiz Arena runtime.
- `/opt/api-quiz-bank` exists and owns a separate API Quiz Bank runtime.
- `/opt/infra-caddy` does not exist yet.
- `/opt/quiz-arena-site` does not exist yet.
- `quiz-arena` compose project runs `postgres`, `redis`, `api`, `worker`,
  `beat`, `frontend`, and `caddy` from `/opt/quiz-arena/docker-compose.prod.yml`.
- `api-quiz-bank` compose project runs `api-quiz-bank` and its PostgreSQL
  service from `/opt/api-quiz-bank`.
- Caddy currently belongs to the `quiz-arena` compose project.
- Caddy currently serves both Quiz Arena and API Quiz Bank edge routes.
- Caddy is attached to `quiz-arena_default` and `api-quiz-bank_default`.
- `api-quiz-bank-pilot` is attached to both `api-quiz-bank_default` and
  `quiz-arena_default`.
- Existing Caddy volumes are owned by the `quiz-arena` compose project:
  `quiz-arena_caddy_data` and `quiz-arena_caddy_config`.
- Existing Quiz Arena data volumes are `quiz-arena_pg_data` and
  `quiz-arena_redis_data`.
- Existing API Quiz Bank data volume is
  `api-quiz-bank_api-quiz-bank-postgres-data`.

Current public health checks were OK at inventory time:

- `https://deutchquizarena.de/health` returned `200`.
- `https://deutchquizarena.46.225.181.45.sslip.io/health` returned `200`.
- `https://api.valerchik.de/health` without the API key returned `401`.
- `https://api.valerchik.de/health` with the configured API key returned `200`.
- Telegram webhook URL was `https://deutchquizarena.de/webhook/telegram`.
- Telegram `pending_update_count` was `0`.

## Target State

The target runtime is four compose ownership boundaries:

| Stack | Target path | Services | Owns data |
| --- | --- | --- | --- |
| `quiz-arena` | `/opt/quiz-arena` | `postgres`, `redis`, `api`, `worker`, `beat` | `quiz-arena_pg_data`, `quiz-arena_redis_data` |
| `quiz-arena-site` | `/opt/quiz-arena-site` | `frontend` | none |
| `api-quiz-bank` | `/opt/api-quiz-bank` | `api-quiz-bank`, `api-quiz-bank-postgres` | `api-quiz-bank_api-quiz-bank-postgres-data` |
| `infra-caddy` | `/opt/infra-caddy` | `caddy` | reuses `quiz-arena_caddy_data`, `quiz-arena_caddy_config` as external volumes |

Services that remain in `quiz-arena`:

- `postgres`
- `redis`
- `api`
- `worker`
- `beat`

Services that move to `quiz-arena-site`:

- `frontend`

Services that move to `infra-caddy`:

- `caddy`
- Active edge Caddyfile.
- Caddy TLS/storage volumes, mounted as external existing volumes.

Services that remain in `api-quiz-bank`:

- `api-quiz-bank`
- `api-quiz-bank-postgres`

## Upstream Model

Caddy must continue to use the same upstream hostnames:

| Upstream name | Target provider | Network requirement |
| --- | --- | --- |
| `api:8000` | `quiz-arena` service `api` | `api` attached to `quiz-arena-edge` with alias `api`; Caddy also attached |
| `frontend:3000` | `quiz-arena-site` service `frontend` | `frontend` attached to `quiz-arena-site-edge` with alias `frontend`; Caddy also attached |
| `api-quiz-bank:8000` | `api-quiz-bank` service | API Quiz Bank service attached to `api-quiz-bank-edge` with alias `api-quiz-bank`; Caddy also attached |

The `quiz-arena-site` frontend should also attach to `quiz-arena-edge` while
`API_INTERNAL_URL=http://api:8000` remains in use. This preserves server-side
frontend calls to the backend without routing them through the public edge.

## Routes To Preserve 1:1

| Domain | Route | Target upstream or behavior |
| --- | --- | --- |
| `www.deutchquizarena.de` | all | redirect to `https://deutchquizarena.de{uri}` with `308` |
| `deutchquizarena.de` | `/webhook*` | `api:8000` |
| `deutchquizarena.de` | `/health` | `api:8000` |
| `deutchquizarena.de` | `/api/ready`, `/api/ready/*` | public `404` |
| `deutchquizarena.de` | `/api/quiz-teaser/*` | `frontend:3000` |
| `deutchquizarena.de` | `/api/*` | `api:8000` with path prefix stripped by `handle_path` |
| `deutchquizarena.de` | fallback | `frontend:3000` |
| `deutchquizarena.46.225.181.45.sslip.io` | same as `deutchquizarena.de` | same behavior |
| `api.valerchik.de` | missing or wrong `X-API-Key` | `401` |
| `api.valerchik.de` | authorized requests | `api-quiz-bank:8000` |

## Proposed Local Files

Prepared draft target files:

- `deploy/infra-caddy/docker-compose.yml`
- `deploy/infra-caddy/Caddyfile`
- `deploy/quiz-arena/docker-compose.prod.yml`
- `deploy/quiz-arena-site/docker-compose.prod.yml`

These are target layout drafts for review. They must not be copied to the VPS
or executed until a separate migration task is approved.

## Network Plan

External Docker networks to create during the future migration:

| Network | Created by | Connected services | Required aliases |
| --- | --- | --- | --- |
| `quiz-arena-edge` | Phase 2 operator command | `infra-caddy/caddy`, `quiz-arena/api`, `quiz-arena-site/frontend` while it needs backend SSR access | `api` on backend service |
| `quiz-arena-site-edge` | Phase 2 operator command | `infra-caddy/caddy`, `quiz-arena-site/frontend` | `frontend` on frontend service |
| `api-quiz-bank-edge` | Phase 2 operator command | `infra-caddy/caddy`, `api-quiz-bank/api-quiz-bank` | `api-quiz-bank` on API Quiz Bank service |

Network creation commands for the future migration window:

```bash
docker network create quiz-arena-edge
docker network create quiz-arena-site-edge
docker network create api-quiz-bank-edge
```

Run those only after Phase 0 approval. If a network already exists, inspect it
instead of recreating it.

## Caddy Migration Plan

Target owner: `infra-caddy`.

1. Preserve the current Caddyfile content exactly as the starting point.
   The draft target file is `deploy/infra-caddy/Caddyfile`.
2. Reuse existing Caddy volumes as external volumes:
   - `quiz-arena_caddy_data` -> mounted as `/data`.
   - `quiz-arena_caddy_config` -> mounted as `/config`.
3. Do not create new Caddy storage volumes for the first cutover. Reusing the
   existing volumes avoids losing Let's Encrypt certificates and account data.
4. Do not run old Caddy and new Caddy as active public edge containers at the
   same time on ports `80` and `443`.
5. Use a controlled start mode before public cutover:
   - Validate the target Caddyfile syntax.
   - Confirm the new container can resolve `api`, `frontend`, and
     `api-quiz-bank` on the target networks.
   - If a temporary rehearsal container is used, bind it only to loopback
     ports and avoid ACME writes against production certificates.
6. Public cutover is the only planned interruption:
   - Stop/remove only the old `quiz_arena_caddy_prod` container.
   - Start only the new `infra-caddy` Caddy container on ports `80` and `443`.
   - Verify all routes immediately.
7. Keep old compose files and backups until the 24-48h stability window passes
   and cleanup is separately approved.

## Cutover Sequence

### Phase 0: Maintenance freeze / no deploy window

- Announce freeze.
- Block app deploys, frontend image switches, API Quiz Bank deploys, and Caddy
  changes during the window.
- Confirm current health is green before touching infrastructure.

Rollback: no rollback needed; nothing changed.

### Phase 1: Full backup

- Back up `/opt/quiz-arena`, `/opt/api-quiz-bank`, Caddyfile, compose files,
  and all active `.env*` files without printing secret values.
- Back up PostgreSQL data using the existing approved production backup flow.
- Record Docker container, network, image, and volume inventory.

Rollback: restore files from backup only if a later phase modifies them.

### Phase 2: Create external networks

- Create `quiz-arena-edge`, `quiz-arena-site-edge`, and `api-quiz-bank-edge`.
- Do not detach existing networks yet.

Rollback: if no containers are attached, remove the newly created networks.
If containers are attached, first roll back later phases, then remove them.

### Phase 3: Prepare infra-caddy files

- Create `/opt/infra-caddy`.
- Copy the reviewed target `docker-compose.yml` and `Caddyfile`.
- Create `.env.caddy` from the env ownership matrix.
- Do not start Caddy yet.

Rollback: leave the directory in place or move it aside; traffic still uses old
Caddy.

### Phase 4: Start infra-caddy in controlled mode

- Validate config and DNS/upstream resolution without taking public ports from
  the old Caddy.
- Confirm access to `quiz-arena-edge`, `quiz-arena-site-edge`, and
  `api-quiz-bank-edge`.
- Do not write new TLS certificates unless this is the approved cutover step.

Rollback: stop only the controlled-mode infra Caddy container. Old Caddy still
serves traffic.

### Phase 5: Switch traffic from old Caddy to infra-caddy

- Stop only old `quiz_arena_caddy_prod`.
- Start `infra-caddy/caddy` on ports `80` and `443`.
- Reuse `quiz-arena_caddy_data` and `quiz-arena_caddy_config` as external
  volumes.

Rollback: stop infra Caddy, restart old `quiz_arena_caddy_prod` from the old
`quiz-arena` compose file, then verify routes.

### Phase 6: Verify all routes

- Run the full verification checklist below.
- Do not proceed if Telegram webhook or API Quiz Bank edge is not green.

Rollback: same as Phase 5.

### Phase 7: Detach old Caddy from quiz-arena stack

- Update the future `quiz-arena` compose file to remove `caddy`.
- Keep backend `api` attached to `quiz-arena-edge`.
- Do not restart PostgreSQL or Redis.

Rollback: restore the old `quiz-arena` compose file and run only the old Caddy
service recovery path.

### Phase 8: Split frontend/site

- Create `/opt/quiz-arena-site`.
- Move frontend service ownership into `quiz-arena-site`.
- Attach frontend to `quiz-arena-site-edge` with alias `frontend`.
- Keep frontend attached to `quiz-arena-edge` while it needs
  `API_INTERNAL_URL=http://api:8000`.

Rollback: restore frontend service in the old `quiz-arena` compose stack and
point Caddy back to the old `frontend` upstream if needed.

### Phase 9: Split env files

- Create `.env.quiz-arena`, `.env.site`, `.env.quiz-bank`, and `.env.caddy`
  from the matrix.
- Do not delete the old `.env` until all stacks are verified and backups are
  confirmed.
- Never print values during the split.

Rollback: restore the previous `.env` files from backup and run the previous
compose commands with the previous `--env-file` arguments.

### Phase 10: Stability window 24-48h

- Watch Caddy logs, API logs, worker logs, Telegram webhook status, API Quiz
  Bank edge, Redis queues, and Celery counts.
- No cleanup during this window.

Rollback: use Phase 5/8/9 rollback depending on the failure source.

### Phase 11: Cleanup only after approval

- Remove obsolete compose service definitions, old unused networks, and old
  redundant files only after separate approval.
- Do not delete backups in the migration task.

Rollback: cleanup should happen only after the rollback window is closed. If
cleanup was premature, restore from backups.

## Rollback Checks

After any rollback, verify:

- `https://deutchquizarena.de/health` returns `200`.
- `https://deutchquizarena.46.225.181.45.sslip.io/health` returns `200`.
- Telegram webhook URL is `https://deutchquizarena.de/webhook/telegram`.
- Telegram `pending_update_count` is not increasing.
- `https://api.valerchik.de/health` without key returns `401`.
- Authorized API Quiz Bank edge check returns `200` or at least not `502`.
- Caddy logs show no upstream resolution failures.

## Verification Checklist

Run after future migration:

- `https://deutchquizarena.de/health`
- `https://deutchquizarena.46.225.181.45.sslip.io/health`
- Telegram webhook URL.
- Telegram `pending_update_count`.
- Public `/api/ready` returns `404`.
- `/api/*` routes reach Quiz Arena API.
- `/api/quiz-teaser/*` reaches frontend.
- Frontend loads at `https://deutchquizarena.de`.
- API Quiz Bank unauthorized request returns `401`.
- API Quiz Bank authorized request returns `200` or at least not `502`.
- DB users count is unchanged from the pre-cutover snapshot except for real
  production usage.
- Redis queues: `q_high`, `q_normal`, `q_low`, `celery`.
- Celery `active`, `reserved`, and `scheduled` counts.
- Caddy logs.
- API logs.
- Worker logs.

## Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| TLS certificates lost or regenerated incorrectly | Public HTTPS outage or rate-limit risk | Reuse `quiz-arena_caddy_data` and `quiz-arena_caddy_config` as external volumes; back them up before cutover |
| Wrong Docker aliases | Caddy returns `502` | Preserve aliases `api`, `frontend`, `api-quiz-bank`; test resolution before public cutover |
| Caddy cannot see upstream networks | Quiz Arena or API Quiz Bank outage | Attach Caddy to all three edge networks |
| Telegram webhook gets `502` or connection refused | Bot stops receiving updates | Verify `/webhook* -> api:8000` immediately after cutover; roll back Caddy first |
| `api.valerchik.de` returns `502` | Quiz Bank API unavailable | Keep `api-quiz-bank-edge` alias and verify authorized edge route before proceeding |
| Frontend cannot reach Quiz Bank API | Quiz teaser/site failures | Keep site env keys split and verify `/api/quiz-teaser/*` plus frontend runtime logs |
| Frontend cannot reach Quiz Arena API server-side | SSR/API failures | Keep frontend attached to `quiz-arena-edge` while `API_INTERNAL_URL=http://api:8000` is used |
| Env files mixed after split | Wrong secrets in wrong stack | Split by matrix, review key names only, never copy values through chat/logs |
| Accidental PostgreSQL or Redis restart | Production state risk | Do not include DB/Redis in Caddy or site cutover commands; avoid stack-wide `up/down/restart` |

## Final Decision Gate

Preparing the migration is GO.

Executing the migration is NO-GO until:

- A maintenance freeze is approved.
- Fresh backups are complete.
- Exact commands are reviewed.
- Rollback owner and verification owner are assigned.
- The operator confirms no stack-wide restart commands will be used.
