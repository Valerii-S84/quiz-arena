# Schema Quick Map

High-level database map for current runtime.
Source: `app/db/models/*.py` and active migrations in `alembic/versions/`.

Last verified: 2026-07-18 against current SQLAlchemy models and the migration
that removes the legacy `mode_access` table.

## 1) Identity, Admin, and Public Intake

| Table | Purpose | PK | Key FKs |
|---|---|---|---|
| `users` | Telegram user profile and account state | `id` | `referred_by_user_id -> users.id` |
| `admins` | Admin identities and roles | `id` (UUID) | - |
| `admin_audit_log` | Admin action audit trail | `id` | - |
| `contact_requests` | Public student/partner contact submissions | `id` | - |

Notes:
- External identity key: `telegram_user_id` (unique).
- Stores referral/account status and activity timestamps.

## 2) Gameplay and Progress

| Table | Purpose | PK | Key FKs |
|---|---|---|---|
| `quiz_questions` | Question bank | `question_id` | - |
| `quiz_sessions` | Per-run gameplay session | `id` (UUID) | `user_id -> users.id`, `daily_run_id -> daily_runs.id`, `friend_challenge_id -> friend_challenges.id` |
| `quiz_attempts` | Answer attempts per session | `id` | `session_id -> quiz_sessions.id`, `user_id -> users.id` |
| `mode_progress` | User progress per mode | `(user_id, mode_code)` | `user_id -> users.id` |
| `daily_question_sets` | Daily challenge question set | `(berlin_date, position)` | - |
| `daily_runs` | User daily challenge run | `id` (UUID) | `user_id -> users.id` |
| `daily_push_logs` | Push dedupe log for daily challenge | `(user_id, berlin_date)` | `user_id -> users.id` |
| `friend_challenges` | Duel/challenge lifecycle | `id` (UUID) | `creator_user_id/opponent_user_id/winner_user_id -> users.id` |
| `arena_duels` | Published arena duel definition and baseline | `id` (UUID) | `creator_user_id -> users.id`, `source_friend_challenge_id -> friend_challenges.id` |
| `arena_attempts` | Creator/challenger attempts for arena duels | `id` (UUID) | `arena_duel_id -> arena_duels.id`, `user_id -> users.id` |
| `tournaments` | Tournament header (private/daily arena) | `id` (UUID) | `created_by -> users.id` |
| `tournament_participants` | Participants + standings | `(tournament_id, user_id)` | `tournament_id -> tournaments.id`, `user_id -> users.id` |
| `tournament_matches` | Tournament round pairings/results | `id` (UUID) | `tournament_id -> tournaments.id`, `user_a/user_b/winner_id -> users.id`, `friend_challenge_id -> friend_challenges.id` |
| `tournament_round_scores` | Per-player round score/timing facts | `id` (UUID) | `tournament_id -> tournaments.id`, `player_id/opponent_id -> users.id` |

## 3) Economy, Payments, Promo, Referrals

| Table | Purpose | PK | Key FKs |
|---|---|---|---|
| `energy_state` | Free/paid energy state per user | `user_id` | `user_id -> users.id` |
| `purchases` | Payment lifecycle and Telegram billing metadata | `id` (UUID) | `user_id -> users.id`, `applied_promo_code_id -> promo_codes.id` |
| `telegram_update_inbox` | Sanitized Telegram payment-update evidence and processing state | `update_id` | - |
| `payment_events` | Idempotent normalized payment events | `id` | `source_inbox_update_id -> telegram_update_inbox.update_id` |
| `payment_reconciliation_reviews` | Manual review queue for payment mismatches | `id` | `payment_event_id -> payment_events.id` |
| `entitlements` | Time-bounded rights (premium/mode access/etc.) | `id` | `user_id -> users.id`, `source_purchase_id -> purchases.id` |
| `ledger_entries` | Append-only economy ledger | `id` | `user_id -> users.id`, `purchase_id -> purchases.id` |
| `promo_codes` | Promo campaign/code definition | `id` | - |
| `promo_redemptions` | Per-user promo redemption state machine | `id` (UUID) | `promo_code_id -> promo_codes.id`, `user_id -> users.id`, `applied_purchase_id -> purchases.id`, `grant_entitlement_id -> entitlements.id` |
| `promo_attempts` | Promo brute-force/attempt log | `id` | `user_id -> users.id` |
| `promo_code_batches` | Batch metadata for generated promo codes | `id` | - |
| `promo_audit_log` | Admin promo mutations and context | `id` (UUID) | `admin_id -> admins.id`, `promo_code_id -> promo_codes.id` |
| `referrals` | Referral lifecycle + fraud scoring | `id` | `referrer_user_id/referred_user_id -> users.id` |
| `streak_state` | User streak and streak saver counters | `user_id` | `user_id -> users.id` |
| `offers_impressions` | Offer impressions/clicks/conversions | `id` | `user_id -> users.id`, `converted_purchase_id -> purchases.id` |

## 4) Analytics and Operations

| Table | Purpose | PK | Key FKs |
|---|---|---|---|
| `analytics_events` | Event-level product/ops analytics | `id` | `user_id -> users.id` |
| `analytics_daily` | Daily KPI aggregates | `local_date_berlin` | - |
| `daily_metrics` | Admin-facing daily DAU/revenue/activity rollup | `date` | - |
| `user_events` | User activity timeline for admin/ops views | `id` | - |
| `website_events` | Public website page-view and Telegram CTA analytics | `id` (UUID) | - |
| `processed_updates` | Telegram update idempotency/reliability status | `update_id` | - |
| `telegram_delivery_attempts` | Idempotent outbound Telegram delivery attempts | `id` | - |
| `outbox_events` | Operational/reliability event stream | `id` | - |
| `reconciliation_runs` | Payments reconciliation run log | `id` | - |

## 5) Relationship Spine (Most Important Paths)

```text
users
  -> quiz_sessions -> quiz_attempts
  -> arena_attempts -> arena_duels
  -> energy_state
  -> purchases -> (entitlements, ledger_entries, offers_impressions.converted_purchase_id)
  -> promo_redemptions -> (purchases, entitlements)
  -> referrals
  -> friend_challenges <- tournament_matches <- tournaments
  -> tournament_participants -> tournaments
  -> tournament_round_scores -> tournaments

processed_updates -> webhook idempotency/retries status
telegram_update_inbox -> payment_events -> payment_reconciliation_reviews
telegram_delivery_attempts -> outbound Telegram delivery state
outbox_events -> reliability + ops signaling
analytics_events -> analytics_daily aggregation source
website_events -> admin website analytics
```

## 6) Data Integrity Patterns

- Extensive `CheckConstraint` usage for enum-like statuses and numeric ranges.
- Idempotency keys used across mutation-heavy tables (`purchases`, `ledger_entries`, `quiz_sessions`, `quiz_attempts`, `promo_redemptions`, `offers_impressions`, `entitlements`).
- Partial indexes enforce critical uniqueness windows (for example active purchase constraints).
- `ledger_entries` is append-only at ORM level (`before_update` / `before_delete` guarded).

## 7) Update Rule

When adding/changing tables:
1. add Alembic migration,
2. update corresponding model in `app/db/models/`,
3. remove superseded rows after drop migrations,
4. refresh this file to keep schema map accurate.
