from __future__ import annotations

from datetime import datetime, timezone

import structlog

from app.core.config import get_settings
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.session import SessionLocal
from app.workers.celery_app import celery_app
from app.workers.task_heartbeat import run_tracked_async_job

logger = structlog.get_logger(__name__)

TASK_NAME = "app.workers.tasks.premium_expiry.expire_premium_entitlements"
SCHEDULE_KEY = "premium-expiry-lifecycle-hourly"


async def expire_premium_entitlements_async(*, batch_size: int = 500) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    resolved_batch_size = max(1, min(5000, int(batch_size)))
    async with SessionLocal.begin() as session:
        before_count = await EntitlementsRepo.count_expired_active_premium(
            session,
            now_utc=now_utc,
        )
        expired_total = await EntitlementsRepo.expire_active_premium_before(
            session,
            now_utc=now_utc,
            limit=resolved_batch_size,
        )
        after_count = max(0, before_count - expired_total)

    result = {
        "expired_active_before": before_count,
        "expired_total": expired_total,
        "expired_active_remaining": after_count,
    }
    logger.info("premium_expiry_lifecycle_finished", **result)
    return result


@celery_app.task(name=TASK_NAME)
def expire_premium_entitlements(batch_size: int = 500) -> dict[str, int]:
    return run_tracked_async_job(
        task_name=TASK_NAME,
        schedule_key=SCHEDULE_KEY,
        awaitable=expire_premium_entitlements_async(batch_size=batch_size),
    )


def configure_premium_expiry_schedule(app=celery_app, *, enabled: bool | None = None) -> None:
    schedule_enabled = (
        get_settings().premium_expiry_schedule_enabled if enabled is None else enabled
    )
    if not schedule_enabled:
        return
    app.conf.beat_schedule = app.conf.beat_schedule or {}
    app.conf.beat_schedule.update(
        {
            SCHEDULE_KEY: {
                "task": TASK_NAME,
                "schedule": 3600.0,
                "options": {"queue": "q_normal"},
            },
        }
    )


configure_premium_expiry_schedule(celery_app)


__all__ = [
    "SCHEDULE_KEY",
    "TASK_NAME",
    "configure_premium_expiry_schedule",
    "expire_premium_entitlements",
    "expire_premium_entitlements_async",
]
