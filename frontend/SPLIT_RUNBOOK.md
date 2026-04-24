# Frontend Repo Split Runbook

## Goal

Extract `frontend/` into its own Git repository without changing the public routing surface:

- `/` and `/admin` stay on the Next.js frontend
- `/api/*` and `/webhook*` stay on the backend

This file lives inside `frontend/` so it survives the extraction.
Commands that reference monorepo-root `scripts/` are pre-export steps only.
These scripts exist only in the source monorepo before extraction; they are not part of the exported frontend repo.

## Verified frontend boundary

The current frontend directory already carries its own repo-local bootstrap and boundary files:

- `package.json` with `npm run ci`
- `Dockerfile`
- `.env.example`
- `.gitignore`
- `.dockerignore`
- `lib/api-config.ts`
- `lib/api-routes.ts`
- `lib/public-site-config.ts`

## Before Export From The Monorepo

From the monorepo root:

```bash
git checkout main
git pull --ff-only
git status -sb
cd frontend
npm ci
npm run ci
```

Continue only with a clean worktree.

Monorepo-local automation for the same dry-run:

```bash
bash scripts/split_frontend_dry_run.sh --strategy filter-repo --cleanup
```

If the split-prep files are still only in the local `frontend/` working tree and not yet committed on `main`, add:

```bash
--include-working-tree
```

Fallback dry-run with the same script:

```bash
bash scripts/split_frontend_dry_run.sh --strategy subtree --cleanup
```

Monorepo-local actual export without push:

```bash
bash scripts/export_frontend_repo.sh \
  --strategy filter-repo \
  --include-working-tree \
  --output-dir .tmp/frontend-repo-export \
  --remote-url <new-frontend-repo-url>
```

## Manual Extraction: `git filter-repo`

Use this when `git filter-repo` is available. It produces the cleanest standalone history rewrite.

```bash
git clone --branch main git@github.com:Valerii-S84/quiz-arena.git quiz-arena-frontend
cd quiz-arena-frontend
git filter-repo --path frontend/ --path-rename frontend/:
git remote remove origin
git remote add origin <new-frontend-repo-url>
npm ci
cp .env.example .env.local
npm run ci
git push -u origin main
```

## Manual Fallback: `git subtree split`

Use this when `git filter-repo` is unavailable.

From the monorepo root:

```bash
git checkout main
git pull --ff-only
git subtree split --prefix=frontend -b split/frontend-root
git push <new-frontend-repo-url> split/frontend-root:main
git branch -D split/frontend-root
```

Then validate from a fresh clone of the new frontend repo:

```bash
git clone --branch main <new-frontend-repo-url> quiz-arena-frontend
cd quiz-arena-frontend
npm ci
cp .env.example .env.local
npm run ci
```

## After Export In The Standalone Repo

After the extraction is complete, this repo no longer contains the monorepo-root helper scripts above.
At that point, use only the standalone repo root plus the backend integration points below.

## Backend repo after the split

The backend repo keeps:

- `app/`
- `alembic/`
- backend `Dockerfile`
- backend `scripts/`
- `QuizBank/`
- `app/ops_ui/site`
- reverse-proxy / compose / deploy orchestration for the first iteration

## Integration points that must not change in the first cutover

- Reverse-proxy layout stays the same: `/` and `/admin` to frontend, `/api/*` and `/webhook*` to backend
- Admin auth/session cookies stay on the same host/path surface
- Browser-facing API calls should keep using the same-host `/api` path in production
- SSR and server-side session checks must keep using `API_INTERNAL_URL`
- Frontend route consumption stays centralized in `lib/api-routes.ts`
- Public Telegram link config stays centralized in `lib/public-site-config.ts`
- The first split should not move admin auth to a different subdomain

## Post-split validation

Local validation from the new frontend repo root:

```bash
npm ci
cp .env.example .env.local
npm run ci
docker build \
  -f Dockerfile \
  . \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 \
  --build-arg API_INTERNAL_URL=http://localhost:8000 \
  --build-arg NEXT_PUBLIC_TELEGRAM_BOT_URL=https://t.me/Deine_Deutsch_Quiz_bot \
  --build-arg NEXT_PUBLIC_TELEGRAM_CHANNEL_URL=https://t.me/doechkurse
```

Local environment note for this machine:

- Use a mounted filesystem path such as `/mnt/c/...` for standalone validation
- Avoid WSL-only paths such as `/tmp/...` for `npm` commands here, because the Windows `npm` executable falls back to a UNC current directory and fails before reading `package.json`

Staging smoke scenarios after wiring the new frontend image:

- public stats load
- contact submit
- admin login
- admin 2FA verify
- admin session check
- admin logout
- admin dashboard load
