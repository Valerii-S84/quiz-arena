# Quiz Arena Frontend (Public + Admin)

## Run

```bash
cd frontend
npm install
npm run dev
```

Set API base URL:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Routes

- Public: `/`, `/projects`, `/contact`
- Admin: `/admin/login`, `/admin/dashboard`, `/admin/economy`, `/admin/users`, `/admin/promo`, `/admin/content`, `/admin/system`

## Notes

- Public pages use ISR (`revalidate = 3600`).
- `robots.txt` disallows `/admin`.
- Admin pages require backend cookie session (`/admin/auth/*`).
