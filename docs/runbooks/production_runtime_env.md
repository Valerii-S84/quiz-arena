# Production Runtime Env

Production keeps real values only in `/opt/quiz-arena/.env` on the server.

Required runtime variables for the tracked production compose and Caddy config:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `FRONTEND_IMAGE`
- `FRONTEND_API_INTERNAL_URL` (optional, defaults to `http://api:8000`)
- `DOMAIN`
- `CADDY_EMAIL`
- `QUIZ_BANK_API_BASE_URL`
- `QUIZ_BANK_EDGE_API_KEY`
- `QUIZ_BANK_CONSUMER_ID`
- `QUIZ_BANK_CONSUMER_API_KEY`
- `API_QUIZ_BANK_PUBLIC_API_KEY`

Do not commit real tokens, passwords, keys, or full production `.env` files.
