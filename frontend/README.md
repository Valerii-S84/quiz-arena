# Quiz Arena Frontend (Public + Admin)

## Run

```bash
cd frontend
npm ci
npm run dev
```

Set API URLs:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
API_INTERNAL_URL=http://localhost:8000
```

- `NEXT_PUBLIC_API_URL` is the browser-facing API base.
- In production behind the reverse proxy, prefer a relative `/api`.
- If `NEXT_PUBLIC_API_URL` is absolute, it must already point to the API base, for example `https://deutchquizarena.de/api`.
- `API_INTERNAL_URL` is server-only and used by SSR/admin session checks.
- If `NEXT_PUBLIC_API_URL` is relative, set `API_INTERNAL_URL` explicitly for SSR.
- If `API_INTERNAL_URL` is unset, SSR falls back to an absolute `NEXT_PUBLIC_API_URL` or `http://localhost:8000`.

## Quality Gates

```bash
npm run lint
npm run build
npm test
```

`npm run lint` uses the repo-supported ESLint CLI path.

## Routes

- Public: `/`, `/projects`, `/contact`
- Admin: `/admin/login`, `/admin/dashboard`, `/admin/economy`, `/admin/users`, `/admin/promo`, `/admin/content`, `/admin/system`

## Notes

- Public pages use ISR (`revalidate = 3600`).
- `robots.txt` disallows `/admin`.
- Admin pages require backend cookie session (`/admin/auth/*`).
- The frontend-consumed backend API contract is centralized in `lib/api-routes.ts`.
