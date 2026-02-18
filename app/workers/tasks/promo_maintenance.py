from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog

from app.db.repo.promo_repo import PromoRepo
from app.db.session import SessionLocal
from app.services.alerts import send_ops_alert
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)
PROMO_BRUTEFORCE_LOOKBACK_WINDOW = timedelta(minutes=10)
PROMO_BRUTEFORCE_MIN_FAILED_ATTEMPTS = 100
PROMO_BRUTEFORCE_MIN_DISTINCT_USERS = 2


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


async def run_promo_bruteforce_guard_async() -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    since_utc = now_utc - PROMO_BRUTEFORCE_LOOKBACK_WINDOW

    async with SessionLocal.begin() as session:
        abusive_hashes = await PromoRepo.get_abusive_code_hashes(
            session,
            since_utc=since_utc,
            min_failed_attempts=PROMO_BRUTEFORCE_MIN_FAILED_ATTEMPTS,
            min_distinct_users=PROMO_BRUTEFORCE_MIN_DISTINCT_USERS,
        )
        paused_campaigns = await PromoRepo.pause_active_codes_by_hashes(
            session,
            code_hashes=abusive_hashes,
            now_utc=now_utc,
        )

    result = {
        "abusive_hashes": len(abusive_hashes),
        "paused_campaigns": paused_campaigns,
    }
    if paused_campaigns > 0:
        await send_ops_alert(
            event="promo_campaign_auto_paused",
            payload=result,
        )
        logger.warning("promo_campaign_auto_paused", **result)
    else:
        logger.info("promo_bruteforce_guard_finished", **result)
    return result


@celery_app.task(name="app.workers.tasks.promo_maintenance.run_promo_reservation_expiry")
def run_promo_reservation_expiry() -> dict[str, int]:
    return asyncio.run(run_promo_reservation_expiry_async())


@celery_app.task(name="app.workers.tasks.promo_maintenance.run_promo_campaign_status_rollover")
def run_promo_campaign_status_rollover() -> dict[str, int]:
    return asyncio.run(run_promo_campaign_status_rollover_async())


@celery_app.task(name="app.workers.tasks.promo_maintenance.run_promo_bruteforce_guard")
def run_promo_bruteforce_guard() -> dict[str, int]:
    return asyncio.run(run_promo_bruteforce_guard_async())


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
        "promo-bruteforce-guard-every-minute": {
            "task": "app.workers.tasks.promo_maintenance.run_promo_bruteforce_guard",
            "schedule": 60.0,
            "options": {"queue": "q_normal"},
        },
    }
)
