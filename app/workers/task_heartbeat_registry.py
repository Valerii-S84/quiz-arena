from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True, slots=True)
class CriticalTaskHeartbeat:
    task_name: str
    schedule_key: str
    stale_after_seconds: int | None
    severity: str = "P1"


CRITICAL_TASK_HEARTBEATS: tuple[CriticalTaskHeartbeat, ...] = (
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.telegram_updates_observability.run_telegram_updates_reliability_alerts",
        schedule_key="telegram-updates-reliability-alerts-every-5-minutes",
        stale_after_seconds=600,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.payments_reliability.recover_paid_uncredited",
        schedule_key="recover-paid-uncredited-every-5-minutes",
        stale_after_seconds=600,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.payments_reliability.run_payment_invariant_alerts",
        schedule_key="payment-invariant-alerts-every-minute",
        stale_after_seconds=120,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.payments_reliability.expire_stale_unpaid_invoices",
        schedule_key="expire-stale-unpaid-invoices-every-5-minutes",
        stale_after_seconds=600,
        severity="P2",
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.payments_reliability.run_refund_promo_rollback",
        schedule_key="refund-promo-rollback-every-5-minutes",
        stale_after_seconds=600,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.payments_reliability.run_payments_reconciliation",
        schedule_key="payments-reconciliation-every-15-minutes",
        stale_after_seconds=1800,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.payments_reliability.run_telegram_stars_reconciliation",
        schedule_key="telegram-stars-reconciliation-every-5-minutes",
        stale_after_seconds=600,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.daily_cup.send_invite",
        schedule_key="daily-cup-send-invite-on-demand",
        stale_after_seconds=None,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.daily_cup.send_invite_registration",
        schedule_key="daily-cup-send-invite-registration",
        stale_after_seconds=172800,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.daily_cup.open_registration",
        schedule_key="daily-cup-open-registration",
        stale_after_seconds=None,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.daily_cup.send_last_call_reminder",
        schedule_key="daily-cup-last-call-reminder",
        stale_after_seconds=172800,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.daily_cup.send_prestart_reminder",
        schedule_key="daily-cup-prestart-reminder",
        stale_after_seconds=172800,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.daily_cup.send_turn_reminders",
        schedule_key="daily-cup-turn-reminders",
        stale_after_seconds=1200,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.daily_cup.close_registration_and_start",
        schedule_key="daily-cup-close-registration",
        stale_after_seconds=172800,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.daily_cup.publish_final_results",
        schedule_key="daily-cup-publish-final-results",
        stale_after_seconds=172800,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.daily_cup.advance_rounds",
        schedule_key="daily-cup-round-advance",
        stale_after_seconds=120,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.daily_cup.run_daily_cup_round_messaging",
        schedule_key="daily-cup-round-messaging-on-demand",
        stale_after_seconds=None,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.analytics_daily.run_analytics_daily_aggregation",
        schedule_key="analytics-daily-aggregation-hourly",
        stale_after_seconds=7200,
        severity="P2",
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.arena_duels.expire_arena_duels",
        schedule_key="arena-duel-expiry-every-5-minutes",
        stale_after_seconds=600,
        severity="P2",
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.tournaments.run_private_tournament_rounds",
        schedule_key="private-tournaments-round-lifecycle",
        stale_after_seconds=600,
        severity="P1",
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.tournaments_messaging.run_private_tournament_round_messaging",
        schedule_key="private-tournament-round-messaging-on-demand",
        stale_after_seconds=None,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.arena_duels.send_arena_beaten_notification_task",
        schedule_key="arena-beaten-notification-on-demand",
        stale_after_seconds=None,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.offers_observability.run_offers_funnel_alerts",
        schedule_key="offers-funnel-alerts-every-15-minutes",
        stale_after_seconds=1800,
        severity="P2",
    ),
)

_PREMIUM_EXPIRY_HEARTBEAT = CriticalTaskHeartbeat(
    task_name="app.workers.tasks.premium_expiry.expire_premium_entitlements",
    schedule_key="premium-expiry-lifecycle-hourly",
    stale_after_seconds=7200,
    severity="P2",
)


def get_critical_task_heartbeats(
    *,
    premium_expiry_schedule_enabled: bool | None = None,
) -> tuple[CriticalTaskHeartbeat, ...]:
    expiry_enabled = (
        get_settings().premium_expiry_schedule_enabled
        if premium_expiry_schedule_enabled is None
        else premium_expiry_schedule_enabled
    )
    if expiry_enabled:
        return (*CRITICAL_TASK_HEARTBEATS, _PREMIUM_EXPIRY_HEARTBEAT)
    return CRITICAL_TASK_HEARTBEATS
