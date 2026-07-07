# Events Catalog

Catalog of runtime product/operational events as implemented in code.

## 1) Event Streams

1. `analytics_events` (DB table)
- Product + gameplay + economy + tournament analytics.
- Written via `app.core.analytics_events.emit_analytics_event`.

2. `outbox_events` (DB table)
- Reliability/ops-oriented event stream.
- Written via `app.db.repo.outbox_events_repo.OutboxEventsRepo.create`.

3. Ops alert events (external delivery)
- Delivered via `app.services.alerts.send_ops_alert` to configured channels (`generic/slack/pagerduty`).
- These are not a separate DB table by default (except some mirrored events also written to `outbox_events`).

## 2) `analytics_events` Catalog

### 2.1 Channel bonus

| Event | Producer(s) | Primary consumer(s) |
|---|---|---|
| `channel_bonus_shown` | `app/bot/handlers/channel_bonus.py`, gameplay flows (`answer_flow.py`, `energy_zero_flow.py`) | `analytics_daily` (indirect context), internal analytics dashboards |
| `channel_bonus_check_started` | `app/bot/handlers/channel_bonus.py` | internal analytics dashboards |
| `channel_bonus_claimed` | `app/bot/handlers/channel_bonus.py` | internal analytics dashboards |
| `channel_bonus_check_failed_not_subscribed` | `app/bot/handlers/channel_bonus.py` | internal analytics dashboards |
| `channel_bonus_check_failed_error` | `app/bot/handlers/channel_bonus.py` | internal analytics dashboards |

### 2.2 Daily challenge and core gameplay

| Event | Producer(s) | Primary consumer(s) |
|---|---|---|
| `daily_started` | `app/game/sessions/service/sessions_start_daily.py` | internal analytics dashboards |
| `daily_completed` | `app/game/sessions/service/sessions_submit_daily.py` | internal analytics dashboards |
| `daily_abandoned` | `app/game/sessions/service/sessions_daily.py` | internal analytics dashboards |
| `daily_blocked_already_played` | `app/game/sessions/service/sessions_start_daily.py` | internal analytics dashboards |
| `gameplay_energy_zero` | `app/economy/energy/energy_consume.py` | `analytics_daily` aggregation + dashboards |
| `streak_lost` | `app/economy/streak/service.py` | `analytics_daily` aggregation + dashboards |

### 2.3 Daily Cup

| Event | Producer(s) | Primary consumer(s) |
|---|---|---|
| `daily_cup_registered` | `app/bot/handlers/gameplay_flows/daily_cup_flow.py` | internal analytics dashboards |
| `daily_cup_final_viewed` | `app/bot/handlers/gameplay_flows/daily_cup_flow.py` | internal analytics dashboards |
| `daily_cup_result_shared` | `app/bot/handlers/gameplay_flows/daily_cup_flow.py` | internal analytics dashboards |
| `daily_cup_started` | `app/workers/tasks/daily_cup_async.py` | internal analytics dashboards |
| `daily_cup_canceled` | `app/workers/tasks/daily_cup_async.py` | internal analytics dashboards |
| `daily_cup_round_started` | `app/workers/tasks/daily_cup_async.py`, `app/workers/tasks/daily_cup_rounds.py`, session service path for cup match progress | internal analytics dashboards |
| `daily_cup_match_completed` | `app/workers/tasks/daily_cup_rounds.py`, session service path | internal analytics dashboards |

### 2.4 Duel / friend challenge

| Event | Producer(s) | Primary consumer(s) |
|---|---|---|
| `friend_challenge_series_started` | `app/game/sessions/service/friend_challenges_series.py` | internal analytics dashboards |
| `friend_challenge_series_game_created` | `app/game/sessions/service/friend_challenges_series.py` | internal analytics dashboards |
| `friend_challenge_last_chance_sent` | `app/workers/tasks/friend_challenges_async.py` | internal analytics dashboards |
| `friend_challenge_expired_notice_sent` | `app/workers/tasks/friend_challenges_async.py` | internal analytics dashboards |
| `duel_expired` | duel analytics service + worker expiry path | internal analytics dashboards |
| `duel_canceled_by_creator` | `app/game/sessions/service/friend_challenges_manage.py` | internal analytics dashboards |
| `duel_menu_opened` | `app/bot/handlers/gameplay_duels.py` | `analytics_daily` aggregation + dashboards |
| `duel_mode_selected` | `app/bot/handlers/gameplay_duels.py` | `analytics_daily` aggregation + dashboards |
| `friend_duel_opened` | `app/bot/handlers/gameplay_duels.py` | `analytics_daily` aggregation + dashboards |
| `friend_duel_created` | `app/game/sessions/service/friend_challenges_analytics.py`, `app/game/arena_duels/service.py` | `analytics_daily` aggregation + dashboards |
| `friend_duel_share_clicked` | `app/bot/handlers/gameplay_flows/proof_card_flow.py` | `analytics_daily` aggregation + dashboards |
| `friend_duel_joined` | `app/game/sessions/service/friend_challenges_join.py` | `analytics_daily` aggregation + dashboards |
| `friend_duel_started` | `app/game/sessions/service/friend_challenges_rounds.py` | `analytics_daily` aggregation + dashboards |
| `friend_duel_completed` | `app/game/sessions/service/sessions_submit_friend_challenge.py` | `analytics_daily` aggregation + dashboards |
| `friend_duel_revanche_clicked` | `app/game/sessions/service/friend_challenges_analytics.py` | `analytics_daily` aggregation + dashboards |
| `arena_opened` | `app/bot/handlers/gameplay_flows/arena_duel_flow.py` | `analytics_daily` aggregation + dashboards |
| `arena_duel_created` | `app/game/arena_duels/service.py` | `analytics_daily` aggregation + dashboards |
| `arena_duel_started` | `app/game/arena_duels/service.py`, `app/game/arena_duels/accept.py` | `analytics_daily` aggregation + dashboards |
| `arena_duel_completed` | `app/game/arena_duels/service.py` | `analytics_daily` aggregation + dashboards |
| `arena_duel_published` | `app/game/arena_duels/service.py`, `app/bot/handlers/gameplay_flows/arena_duel_flow.py` | `analytics_daily` aggregation + dashboards |
| `arena_duel_accepted` | `app/game/arena_duels/accept.py` | `analytics_daily` aggregation + dashboards |
| `arena_result_shown` | `app/bot/handlers/gameplay_flows/arena_duel_flow.py` | `analytics_daily` aggregation + dashboards |
| `arena_result_beaten_notification_sent` | `app/workers/tasks/arena_duels.py` | `analytics_daily` aggregation + dashboards |
| `arena_revanche_clicked` | `app/bot/handlers/gameplay_flows/arena_revanche_flow.py` | `analytics_daily` aggregation + dashboards |
| `friend_duel_published_to_arena` | `app/bot/handlers/gameplay_flows/arena_duel_flow.py` | `analytics_daily` aggregation + dashboards |
| `duel_limit_hit` | `app/bot/handlers/gameplay_flows/arena_duel_flow.py` | `analytics_daily` aggregation + dashboards |
| `duel_paywall_shown` | `app/bot/handlers/gameplay_flows/arena_duel_flow.py` | `analytics_daily` aggregation + dashboards |
| `duel_ticket_clicked` | `app/bot/handlers/payments.py` | `analytics_daily` aggregation + dashboards |
| `premium_week_clicked` | `app/bot/handlers/payments.py` | `analytics_daily` aggregation + dashboards |

Arena/Duelle payload contract:
- `user_id`: app user id when the event is user-scoped.
- `friend_challenge_id`: Freundesduell UUID when the event is tied to a friend duel.
- `arena_duel_id`: Arena duel UUID when the event is tied to one duel.
- `attempt_id`: Arena attempt UUID for start/completion/accept events.
- `action`: compact action label such as `menu`, `arena`, `friend`, `create`, `accept`, `creator_baseline`, `challenger`, `publish_friend`, or `buy`.
- `access_type`: resolved duel access type (`FREE`, `PAID_TICKET`, `PREMIUM`) or clicked duel product code for paywall click events.
- `result`: Arena result code when a result exists.
- `score`: completed score when known.
- `time_ms`: completed time in milliseconds when known.

Friend duel funnel rule:
- Use `friend_duel_opened`, `friend_duel_created`, `friend_duel_joined`, `friend_duel_started`, `friend_duel_completed`, `friend_duel_share_clicked`, `friend_duel_revanche_clicked`, and `friend_duel_published_to_arena` as canonical friend-mode events; do not infer them from `duel_mode_selected` or `arena_duel_published` payload actions.

### 2.5 Private tournaments

| Event | Producer(s) | Primary consumer(s) |
|---|---|---|
| `private_tournament_created` | `app/bot/handlers/gameplay_flows/tournament_flow.py` | internal analytics dashboards |
| `private_tournament_joined` | `app/bot/handlers/gameplay_flows/tournament_lobby_flow.py` | internal analytics dashboards |
| `private_tournament_started` | `app/bot/handlers/gameplay_flows/tournament_lobby_flow.py` | internal analytics dashboards |
| `private_tournament_round_started` | `app/workers/tasks/tournaments_async.py` | internal analytics dashboards |
| `private_tournament_completed` | `app/workers/tasks/tournaments_async.py` | internal analytics dashboards |
| `private_tournament_result_shared` | `app/bot/handlers/gameplay_flows/tournament_flow.py` | internal analytics dashboards |

### 2.6 Purchases and referrals

| Event | Producer(s) | Primary consumer(s) |
|---|---|---|
| `purchase_init_created` | `app/economy/purchases/service/init.py` | `analytics_daily` aggregation + dashboards |
| `purchase_invoice_sent` | `app/economy/purchases/service/precheckout.py` | `analytics_daily` aggregation + dashboards |
| `purchase_precheckout_ok` | `app/economy/purchases/service/precheckout.py` | `analytics_daily` aggregation + dashboards |
| `purchase_paid_uncredited` | `app/economy/purchases/service/credit.py` | `analytics_daily` aggregation + dashboards |
| `purchase_credited` | `app/economy/purchases/service/credit.py` | `analytics_daily` aggregation + dashboards |
| `referral_link_shared` | `app/bot/handlers/referral.py` | internal analytics dashboards |
| `referral_prompt_shown` | `app/bot/handlers/gameplay_flows/answer_flow.py` | internal analytics dashboards |
| `referral_reward_claimed` | `app/bot/handlers/referral.py` | internal analytics dashboards |
| `referral_reward_notified` | `app/workers/tasks/referrals_notifications.py` | internal analytics dashboards |
| `referral_reward_milestone_available` | `app/workers/tasks/referrals.py` | `analytics_daily` aggregation + internal referrals ops |
| `referral_reward_granted` | `app/workers/tasks/referrals.py` | `analytics_daily` aggregation + internal referrals ops |

### 2.7 Current `analytics_daily` event subset

The hourly daily aggregator (`app/workers/tasks/analytics_daily.py`) currently counts these event types from `analytics_events`:
- `gameplay_energy_zero`
- `streak_lost`
- `referral_reward_milestone_available`
- `referral_reward_granted`
- `purchase_init_created`
- `purchase_invoice_sent`
- `purchase_precheckout_ok`
- `purchase_paid_uncredited`
- `purchase_credited`
- `duel_menu_opened`
- `duel_mode_selected`
- `arena_opened`
- `arena_duel_created`
- `arena_duel_started`
- `arena_duel_completed`
- `arena_duel_published`
- `arena_duel_accepted`
- `arena_result_shown`
- `arena_result_beaten_notification_sent`
- `arena_revanche_clicked`
- `friend_duel_opened`
- `friend_duel_created`
- `friend_duel_share_clicked`
- `friend_duel_joined`
- `friend_duel_started`
- `friend_duel_completed`
- `friend_duel_published_to_arena`
- `friend_duel_revanche_clicked`
- `duel_limit_hit`
- `duel_paywall_shown`
- `duel_ticket_clicked`
- `premium_week_clicked`

These counters are persisted in `analytics_daily`, surfaced by `app/api/routes/internal_analytics.py`,
and covered by repo/integration tests for the duel funnel aggregation path.

## 3) `outbox_events` Catalog

| Event | Producer(s) | Typical status | Primary consumer(s) |
|---|---|---|---|
| `telegram_update_reclaimed` | telegram update processing reliability path | `SENT` | `app/workers/tasks/telegram_updates_observability.py` |
| `telegram_update_retry_scheduled` | telegram update task retry scheduling | `SENT` | `app/workers/tasks/telegram_updates_observability.py` |
| `telegram_update_failed_final` | telegram update max-retries reached | `SENT` | `app/workers/tasks/telegram_updates_observability.py` |
| `referral_reward_milestone_available` | `app/workers/tasks/referrals.py` | `SENT` or `FAILED` | internal referrals events feed (`/internal/referrals/events`) |
| `referral_reward_granted` | `app/workers/tasks/referrals.py` | `SENT` or `FAILED` | internal referrals events feed (`/internal/referrals/events`) |
| `payments_telegram_stars_reconciliation_review` | `app/workers/tasks/payments_reliability_async.py` | `OPEN` | payment manual review / production state checks |

Notes:
- `outbox_events` is also subject to retention cleanup (`app/workers/tasks/retention_cleanup.py`).
- `payments_telegram_stars_reconciliation_review` is the migration-deferred review mechanism for
  Stars reconciliation findings. Payload stores `reason`, `severity`, hashed `review_key`, hashed
  `transaction_id_hash`, `candidate_purchase_ids`, `candidate_purchase_count`, and
  `raw_payload_stored=false`. It must not contain bot tokens, raw Telegram payloads, raw invoice
  payloads, or raw charge ids. Deduplication is best-effort until a dedicated review table or
  unique constraint is approved.

## 4) Ops Alert Event Catalog (External Channels)

These events are sent through `send_ops_alert(...)` and routed by `app/services/alerts_config.py`:

- `promo_campaign_auto_paused`
- `payments_recovery_review_required`
- `payments_reconciliation_diff_detected`
- `payments_precheckout_stuck_detected`
- `payments_paid_uncredited_stuck_detected`
- `payments_credit_invariant_failed`
- `payments_webhook_allowed_updates_missing`
- `offers_conversion_drop_detected`
- `offers_spam_anomaly_detected`
- `referral_fraud_spike_detected`
- `telegram_updates_reliability_degraded`
- `referral_reward_milestone_available`
- `referral_reward_granted`

## 5) Governance Rule

When adding a new event type:
1. define producer and payload contract,
2. define consumer(s) and alert/dashboard behavior,
3. update this catalog in the same PR.
