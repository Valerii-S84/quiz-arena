from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import TypeVar

import structlog

from app.db.repo.production_reliability_repo import WorkerTaskHeartbeatsRepo, safe_error_hash
from app.db.session import SessionLocal
from app.workers.asyncio_runner import run_async_job

T = TypeVar("T")

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CriticalTaskHeartbeat:
    task_name: str
    schedule_key: str
    stale_after_seconds: int | None
    severity: str = "P1"
    enabled: bool = True


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
        task_name="app.workers.tasks.premium_expiry.expire_premium_entitlements",
        schedule_key="premium-expiry-lifecycle-hourly",
        stale_after_seconds=7200,
        severity="P2",
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.production_invariant_alerts.run_production_invariant_alerts",
        schedule_key="production-critical-invariant-alerts-every-5-minutes",
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
        task_name="app.workers.tasks.tournaments.run_private_tournament_rounds",
        schedule_key="private-tournaments-round-lifecycle",
        stale_after_seconds=600,
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
        task_name="app.workers.tasks.arena_duels.expire_arena_duels",
        schedule_key="arena-duel-expiry-every-5-minutes",
        stale_after_seconds=600,
        severity="P2",
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.offers_observability.run_offers_funnel_alerts",
        schedule_key="offers-funnel-alerts-every-15-minutes",
        stale_after_seconds=1800,
        severity="P2",
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.analytics_daily.run_analytics_daily_aggregation",
        schedule_key="analytics-daily-aggregation-hourly",
        stale_after_seconds=7200,
        severity="P2",
    ),
)


async def run_with_task_heartbeat(
    *,
    task_name: str,
    schedule_key: str,
    awaitable: Awaitable[T],
    session_local=SessionLocal,
) -> T:
    started_at = datetime.now(timezone.utc)
    monotonic_started = monotonic()
    await _record_started(
        task_name=task_name,
        schedule_key=schedule_key,
        started_at=started_at,
        session_local=session_local,
    )
    try:
        result = await awaitable
    except Exception as exc:
        await _record_failure(
            task_name=task_name,
            schedule_key=schedule_key,
            failed_at=datetime.now(timezone.utc),
            duration_ms=_duration_ms(monotonic_started),
            exc=exc,
            session_local=session_local,
        )
        raise
    await _record_success(
        task_name=task_name,
        schedule_key=schedule_key,
        succeeded_at=datetime.now(timezone.utc),
        duration_ms=_duration_ms(monotonic_started),
        session_local=session_local,
    )
    return result


def run_tracked_async_job(*, task_name: str, schedule_key: str, awaitable: Awaitable[T]) -> T:
    return run_async_job(
        run_with_task_heartbeat(
            task_name=task_name,
            schedule_key=schedule_key,
            awaitable=awaitable,
        )
    )


def get_critical_task_heartbeats() -> tuple[CriticalTaskHeartbeat, ...]:
    return CRITICAL_TASK_HEARTBEATS


async def _record_started(*, task_name: str, schedule_key: str, started_at, session_local) -> None:
    try:
        async with session_local.begin() as session:
            await WorkerTaskHeartbeatsRepo.record_started(
                session,
                task_name=task_name,
                schedule_key=schedule_key,
                started_at=started_at,
            )
    except Exception as exc:
        logger.warning(
            "worker_task_heartbeat_start_write_failed",
            task_name=task_name,
            schedule_key=schedule_key,
            error_type=type(exc).__name__,
        )


async def _record_success(
    *,
    task_name: str,
    schedule_key: str,
    succeeded_at,
    duration_ms: int,
    session_local,
) -> None:
    try:
        async with session_local.begin() as session:
            await WorkerTaskHeartbeatsRepo.record_success(
                session,
                task_name=task_name,
                schedule_key=schedule_key,
                succeeded_at=succeeded_at,
                duration_ms=duration_ms,
            )
    except Exception as exc:
        logger.warning(
            "worker_task_heartbeat_success_write_failed",
            task_name=task_name,
            schedule_key=schedule_key,
            error_type=type(exc).__name__,
        )


async def _record_failure(
    *,
    task_name: str,
    schedule_key: str,
    failed_at,
    duration_ms: int,
    exc: Exception,
    session_local,
) -> None:
    try:
        async with session_local.begin() as session:
            await WorkerTaskHeartbeatsRepo.record_failure(
                session,
                task_name=task_name,
                schedule_key=schedule_key,
                failed_at=failed_at,
                duration_ms=duration_ms,
                error_hash=safe_error_hash(exc),
            )
    except Exception as write_exc:
        logger.warning(
            "worker_task_heartbeat_failure_write_failed",
            task_name=task_name,
            schedule_key=schedule_key,
            error_type=type(write_exc).__name__,
        )


def _duration_ms(started: float) -> int:
    return max(0, int((monotonic() - started) * 1000))
