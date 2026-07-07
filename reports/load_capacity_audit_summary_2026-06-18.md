# Quiz Arena Telegram Bot Capacity Audit Summary

Date: 2026-06-18
Tested commit: 594e0b6
Branch: codex/website-visitor-analytics

## Environment

- Isolated database: `quiz_arena_test`
- Redis: local Redis DB 15
- Telegram: synthetic updates only
- Outbound Telegram API: mocked `sendMessage` and `answerCallbackQuery`
- Production bot token: not used
- Production database/users/statistics: not touched
- Production Quiz Bank API: not touched

## Runtime Identified

- Production compose uses webhook ingress through `api`.
- API command: `uvicorn app.main:app --workers ${API_WORKERS:-4}`.
- Telegram updates are enqueued to Celery from `/webhook/telegram`.
- Worker command: `celery -A app.workers.celery_app worker -Q q_high,q_normal,q_low --concurrency=${CELERY_WORKER_CONCURRENCY:-4}`.
- Backend services: PostgreSQL and Redis.
- Polling script exists for local/manual mode, but production compose points to webhook + Celery.

## Registered User Scale Results

| Registered users | DB size | User lookup p95 | Global best streak | Public stats | Question pool warm | RSS |
|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 16.835 MB | 41.204 ms | 41.605 ms | 43.578 ms | 56.164 ms | 185.08 MB |
| 10,000 | 22.093 MB | 41.652 ms | 39.038 ms | 43.964 ms | 49.997 ms | 194.98 MB |
| 100,000 | 73.460 MB | 53.956 ms | 52.691 ms | 55.423 ms | 47.787 ms | 200.00 MB |

## Active Flow Results

| Scenario | Flow | p50 | p95 | max | Errors | SQL queries | Query p95 | Duplicates | Outbound estimate |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 10 users | webhook smoke | 5622.066 ms | 5649.436 ms | 5665.752 ms | 0 | 945 | 77.967 ms | 0 | 50 SendMessage, 20 AnswerCallbackQuery |
| 10 users | service | 1923.573 ms | 1935.725 ms | 1937.309 ms | 0 | 678 | 64.073 ms | 0 | 30 SendMessage, 20 AnswerCallbackQuery |
| 25 users | service | 4689.729 ms | 4701.106 ms | 4711.776 ms | 0 | 1689 | 198.267 ms | 0 | 75 SendMessage, 50 AnswerCallbackQuery |
| 50 users | service | 9542.215 ms | 9648.921 ms | 9655.818 ms | 0 | 3428 | 348.435 ms | 0 | 150 SendMessage, 100 AnswerCallbackQuery |

Gate 3 stopped at 50 active users because p95 was 9.65s. No DB lock spike, deadlock, duplicate answer write, or state corruption was observed.

## Bottlenecks

- Hot path performs roughly 67-69 SQL operations per synthetic quiz flow.
- Repeated home snapshot calls trigger user lookup/touch, energy sync, streak sync, global best streak, entitlement, and badge checks.
- `MAX(streak_state.best_streak)` is in the hot path and uses a sequential scan at 100k synthetic users.
- Entitlement checks, tournament badge checks, question selection, energy/streak state, and user touch/lookup dominate total DB time under concurrency.
- Question pool cache is process-local; each worker can warm its own pool.
- Outbound Telegram volume is not rate-limited by a dedicated send queue in the measured flow.

## What Was Not Touched

- Production Telegram bot token.
- Live Telegram API.
- Production database, users, statistics, or migrations.
- Production Quiz Bank API.
- Deployment files and production compose.
- Any destructive production operation.

## Next Step

Reduce hot-path SQL volume and re-run staged synthetic tests at 10, 25, 50, then 100+ active users only after gates pass.
