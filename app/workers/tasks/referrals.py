from __future__ import annotations

from datetime import datetime, timezone

import structlog
from celery.schedules import crontab

from app.core.analytics_events import EVENT_SOURCE_WORKER, emit_analytics_event
from app.db.repo.outbox_events_repo import OutboxEventsRepo
from app.db.session import SessionLocal
from app.economy.referrals.service import ReferralService
from app.services.alerts import send_ops_alert
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.referrals_notifications import (
    send_referral_ready_notifications as _send_referral_ready_notifications,
)
from app.workers.tasks.referrals_notifications import (
    send_referral_rejected_notifications as _send_referral_rejected_notifications,
)

logger = structlog.get_logger(__name__)
REFERRAL_REWARD_EVENT_TYPES = (
    "referral_reward_milestone_available",
    "referral_reward_granted",
)


async def run_referral_qualification_checks_async(*, batch_size: int = 200) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    rejected_referrer_user_ids: list[int] = []

    async def _collect_rejected_referrer(_referral_id: int, referrer_user_id: int) -> None:
        rejected_referrer_user_ids.append(referrer_user_id)

    async with SessionLocal.begin() as session:
        result = await ReferralService.run_qualification_checks(
            session,
            now_utc=now_utc,
            batch_size=batch_size,
            on_rejected_fraud=_collect_rejected_referrer,
        )
    rejected_notifications = await _send_referral_rejected_notifications(
        referrer_user_ids=rejected_referrer_user_ids
    )
    result = {**result, **rejected_notifications}
    logger.info("referral_qualification_checks_finished", **result)
    return result


async def run_referral_reward_distribution_async(*, batch_size: int = 200) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        result = await ReferralService.run_reward_distribution(
            session,
            now_utc=now_utc,
            batch_size=batch_size,
            reward_code=None,
        )

    notifications_sent = {
        "reward_user_notified": 0,
        "reward_user_notify_failed": 0,
    }
    if result.get("newly_notified", 0) > 0:
        notifications_sent = await _send_referral_ready_notifications(notified_at=now_utc)
    alerts_sent = await _send_referral_reward_alerts(result=result)
    result = {**result, **notifications_sent, **alerts_sent}
    logger.info("referral_reward_distribution_finished", **result)
    return result


async def _send_referral_reward_alerts(*, result: dict[str, int]) -> dict[str, int]:
    milestone_alert_sent = 0
    reward_alert_sent = 0

    if result.get("newly_notified", 0) > 0:
        milestone_event = REFERRAL_REWARD_EVENT_TYPES[0]
        milestone_alert_sent = int(
            await send_ops_alert(
                event=milestone_event,
                payload=result,
            )
        )
        await _record_referral_reward_event(
            event_type=milestone_event,
            payload=result,
            sent=bool(milestone_alert_sent),
        )

    if result.get("rewards_granted", 0) > 0:
        reward_event = REFERRAL_REWARD_EVENT_TYPES[1]
        reward_alert_sent = int(
            await send_ops_alert(
                event=reward_event,
                payload=result,
            )
        )
        await _record_referral_reward_event(
            event_type=reward_event,
            payload=result,
            sent=bool(reward_alert_sent),
        )

    return {
        "milestone_alert_sent": milestone_alert_sent,
        "reward_alert_sent": reward_alert_sent,
    }


async def _record_referral_reward_event(
    *,
    event_type: str,
    payload: dict[str, int],
    sent: bool,
) -> None:
    now_utc = datetime.now(timezone.utc)
    try:
        async with SessionLocal.begin() as session:
            await OutboxEventsRepo.create(
                session,
                event_type=event_type,
                payload={**payload, "delivery_sent": sent},
                status="SENT" if sent else "FAILED",
            )
            await emit_analytics_event(
                session,
                event_type=event_type,
                source=EVENT_SOURCE_WORKER,
                user_id=None,
                payload={**payload, "delivery_sent": sent},
                happened_at=now_utc,
            )
    except Exception:
        logger.exception(
            "referral_reward_event_record_failed",
            event_type=event_type,
        )


@celery_app.task(name="app.workers.tasks.referrals.run_referral_qualification_checks")
def run_referral_qualification_checks(batch_size: int = 200) -> dict[str, int]:
    return run_async_job(run_referral_qualification_checks_async(batch_size=batch_size))


@celery_app.task(name="app.workers.tasks.referrals.run_referral_reward_distribution")
def run_referral_reward_distribution(batch_size: int = 200) -> dict[str, int]:
    return run_async_job(run_referral_reward_distribution_async(batch_size=batch_size))


celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
celery_app.conf.beat_schedule.update(
    {
        "referral-qualification-every-10-minutes": {
            "task": "app.workers.tasks.referrals.run_referral_qualification_checks",
            "schedule": 600.0,
            "options": {"queue": "q_normal"},
        },
        "referral-reward-distribution-every-15-minutes": {
            "task": "app.workers.tasks.referrals.run_referral_reward_distribution",
            "schedule": 900.0,
            "options": {"queue": "q_normal"},
        },
        "referral-deferred-rollover-first-day-0005-berlin": {
            "task": "app.workers.tasks.referrals.run_referral_reward_distribution",
            "schedule": crontab(day_of_month="1", hour=0, minute=5),
            "options": {"queue": "q_normal"},
        },
    }
)
