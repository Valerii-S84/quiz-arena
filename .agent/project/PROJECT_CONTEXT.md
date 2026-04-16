# PROJECT_CONTEXT

Заповни цей файл перед початком роботи агента.

Якщо обов'язкові поля лишаються незаповненими, агент має
зупинитися до початку будь-якої задачі.

## 1. Stack

- Project name: `Quiz Arena` (`quiz-arena-bot`)
- Primary languages: `Python 3.12`, `TypeScript`, `Bash`
- Runtime / platform: `FastAPI + aiogram + Celery on Python 3.12`, `Next.js 15.5.15 / React 18.3.1 frontend`, `Docker Compose local/prod`, `Linux VPS production`
- Main frameworks / libraries: `FastAPI`, `aiogram`, `SQLAlchemy`, `Alembic`, `Celery`, `Redis`, `Pydantic`, `Next.js`, `React`, `Tailwind CSS`
- Data stores: `PostgreSQL`, `Redis`, `QuizBank CSV assets`
- Default user-facing language: `German only for all product-facing UI, bot text, admin UI text, notifications, and other user-visible copy`

## 2. Project structure

- Root entrypoints: `app/main.py`, `app/workers/celery_app.py`, `scripts/run_bot_polling.py`, `frontend/app/`, `docker-compose.yml`, `docker-compose.prod.yml`
- Source directories: `app/`, `frontend/app/`, `frontend/lib/`, `scripts/`, `tools/`
- Test directories: `tests/` (including `tests/integration/`)
- Config / infra directories: `alembic/`, `deploy/`, `.github/workflows/`, `docs/runbooks/`
- Read-only or protected paths: `.agent/core/`, `.env*`, `.github/workflows/`, `deploy/`, `docker-compose.prod.yml`, `frontend/.next/`, `frontend/node_modules/`

## 3. Key commands

| Purpose | Command | Notes |
|---|---|---|
| Test | `make test` | Backend flow prepares `quiz_arena_test`, runs Alembic migrations, then `pytest -q`; frontend unit tests run via `cd frontend && npm test`; full local CI equivalent is `bash scripts/local_ci.sh` |
| Lint | `make lint && make format-check && make type-check` | Python gate is `ruff`, `black --check`, `isort --check-only`, `mypy`; frontend changes additionally use `cd frontend && npm run lint` (`ESLint CLI` over `.js`, `.mjs`, `.cjs`, `.jsx`, `.ts`, `.mts`, `.cts`, `.tsx`) |
| Build | `cd frontend && npm run build` | Frontend has the only explicit app build command; production runtime build uses `docker compose -f docker-compose.prod.yml up -d --build` |
| Dev / Run | `make up` | Starts local `postgres` and `redis`; then use `make run-api`, `make run-worker`, `make run-beat`, and `cd frontend && npm run dev` as needed |

## 4. External dependencies

| System / service | Purpose | Access mode | Notes |
|---|---|---|---|
| `PostgreSQL` | Primary relational database | Local Docker, CI service, prod container | Alembic-managed schema; test DB names are expected to contain `test` |
| `Redis` | Celery broker/result backend and runtime queues/cache | Local Docker, CI service, prod container | Used by worker/beat and health/runtime checks |
| `Telegram Bot API` | Webhook/polling updates and outbound bot messaging | Outbound HTTPS API | Runtime requires `TELEGRAM_BOT_TOKEN`; webhook flow also uses `TELEGRAM_WEBHOOK_SECRET` |
| `GitHub` | Source repository, PR workflow, CI, protected `main` flow | `git` over SSH and GitHub Actions | Routine deploy flow starts from `origin/main` after CI/PR merge |

## 5. Project constraints

- Protected paths: `.agent/core/**`, `.env*`, `.github/workflows/**`, `deploy/**`, `docker-compose.prod.yml`, `frontend/.next/**`, `frontend/node_modules/**`
- Secrets / credentials locations: `.env`, `.env.example`, `.env.production.example`, `.env.backup_before_prod_recovery_*`; real production runtime env lives only at `/opt/quiz-arena/.env` on the server.
- Deploy / production boundaries: Production runs from `/opt/quiz-arena` via `docker-compose.prod.yml` + `deploy/Caddyfile`; public domain is `deutchquizarena.de`; post-deploy checks must cover health, webhook, Celery and Redis.
- Approval-required operations: production deploys; changes to `.github/workflows/**` or CODEOWNERS/branch protection; server-side `.env` handling; changes to deploy/runtime config; migrations or data backfills outside the normal reviewed flow.
- Restricted hosts / environments: production VPS hosting `/opt/quiz-arena` and `deutchquizarena.de`; Telegram production webhook; GitHub protected branch `main`.
- Project-specific forbidden actions: Do not use `.env.production.example` as runtime env; do not deploy from a dirty local tree over production without backup/reclone; do not run production migrations without a backup; do not bypass PR + CI flow into `main`.

## 6. Git settings

- Default / protected branch: `main`
- Branching strategy: `Create a topic branch from origin/main, push it, and open a PR back to main; do not push directly to protected main`
- Merge strategy: `Squash merge into protected main; merged PRs land on main as a single-parent commit even when the PR contained multiple commits`
- PR title format: `One-line title used as the squash-commit subject; preferred format is type(scope): summary, and main receives it as type(scope): summary (#PR)`
- PR requirements: `PR into main`, `passing CI checks lint_unit and integration`, `at least 1 approval`, `stale approvals dismissed on new commits`, `conversation resolution`, `branch up to date`, `linear history`, `CODEOWNERS review for covered paths`

## 7. Active remediation context

- For tasks about repo cleanup, technical debt, stabilization, CI hardening, structural refactor, or follow-up after repository audit, read `.agent/project/TECH_DEBT_REMEDIATION_PLAN.md` before acting.
- Treat `.agent/project/TECH_DEBT_REMEDIATION_PLAN.md` as the ordered project-specific source of truth for debt-remediation priorities unless the user explicitly overrides the order.
