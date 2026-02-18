from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from app.db.repo.promo_repo import PromoRepo
from app.db.session import SessionLocal
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def run_promo_reservation_expiry_async() -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        expired_count = await PromoRepo.expire_reserved_redemptions(session, now_utc=now_utc)

    result = {"expired_redemptions": expired_count}
    logger.info("promo_reservation_expiry_finished", **result)
    return result


async def run_promo_campaign_status_rollover_async() -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        expired_count = await PromoRepo.expire_active_codes(session, now_utc=now_utc)
        depleted_count = await PromoRepo.deplete_active_codes(session, now_utc=now_utc)

    result = {
        "expired_campaigns": expired_count,
        "depleted_campaigns": depleted_count,
        "updated_campaigns": expired_count + depleted_count,
    }
    logger.info("promo_campaign_status_rollover_finished", **result)
    return result


@celery_app.task(name="app.workers.tasks.promo_maintenance.run_promo_reservation_expiry")
def run_promo_reservation_expiry() -> dict[str, int]:
    return asyncio.run(run_promo_reservation_expiry_async())


@celery_app.task(name="app.workers.tasks.promo_maintenance.run_promo_campaign_status_rollover")
def run_promo_campaign_status_rollover() -> dict[str, int]:
    return asyncio.run(run_promo_campaign_status_rollover_async())


celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
celery_app.conf.beat_schedule.update(
    {
        "promo-reservation-expiry-every-minute": {
            "task": "app.workers.tasks.promo_maintenance.run_promo_reservation_expiry",
            "schedule": 60.0,
            "options": {"queue": "q_normal"},
        },
        "promo-campaign-status-rollover-every-10-minutes": {
            "task": "app.workers.tasks.promo_maintenance.run_promo_campaign_status_rollover",
            "schedule": 600.0,
            "options": {"queue": "q_normal"},
        },
    }
)
