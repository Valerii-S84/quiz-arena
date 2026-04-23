# Quiz Arena Frontend (Public + Admin)

## Run

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Set frontend env values:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
API_INTERNAL_URL=http://localhost:8000
NEXT_PUBLIC_TELEGRAM_BOT_URL=https://t.me/Deine_Deutsch_Quiz_bot
NEXT_PUBLIC_TELEGRAM_CHANNEL_URL=https://t.me/doechkurse
```

- `NEXT_PUBLIC_API_URL` is the browser-facing API base.
- In production behind the reverse proxy, prefer a relative `/api`.
- If `NEXT_PUBLIC_API_URL` is absolute, it must already point to the API base, for example `https://deutchquizarena.de/api`.
- `API_INTERNAL_URL` is server-only and used by SSR/admin session checks.
- If `NEXT_PUBLIC_API_URL` is relative, set `API_INTERNAL_URL` explicitly for SSR.
- If `API_INTERNAL_URL` is unset, SSR falls back to an absolute `NEXT_PUBLIC_API_URL` or `http://localhost:8000`.
- `NEXT_PUBLIC_TELEGRAM_BOT_URL` configures the public bot CTA target.
- `NEXT_PUBLIC_TELEGRAM_CHANNEL_URL` configures the public Telegram channel CTA target.

## Docker

Pass the same env contract into the frontend image build/runtime:

```bash
docker build \
  -f Dockerfile \
  . \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 \
  --build-arg API_INTERNAL_URL=http://localhost:8000 \
  --build-arg NEXT_PUBLIC_TELEGRAM_BOT_URL=https://t.me/Deine_Deutsch_Quiz_bot \
  --build-arg NEXT_PUBLIC_TELEGRAM_CHANNEL_URL=https://t.me/doechkurse
```

The Dockerfile accepts all four values in both the `builder` and `production` stages.

## Quality Gates

```bash
npm run lint
npm test
npm run typecheck
npm run build
npm run ci
```

`npm run lint` uses the repo-supported ESLint CLI path.
`npm run ci` is the frontend-local aggregate gate for a standalone repo or future frontend-only CI job.

## Routes

- Public: `/`, `/projects`, `/contact`
- Admin: `/admin/login`, `/admin/dashboard`, `/admin/economy`, `/admin/users`, `/admin/promo`, `/admin/content`, `/admin/system`

## Notes

- Public pages use ISR (`revalidate = 3600`).
- `robots.txt` disallows `/admin`.
- Admin pages require backend cookie session (`/admin/auth/*`).
- The frontend-consumed backend API contract is centralized in `lib/api-routes.ts`.
- The frontend public-link env contract is centralized in `lib/public-site-config.ts`.
