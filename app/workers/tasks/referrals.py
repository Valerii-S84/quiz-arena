from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from celery.schedules import crontab

from app.db.session import SessionLocal
from app.economy.referrals.service import ReferralService
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def run_referral_qualification_checks_async(*, batch_size: int = 200) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        result = await ReferralService.run_qualification_checks(
            session,
            now_utc=now_utc,
            batch_size=batch_size,
        )
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
    logger.info("referral_reward_distribution_finished", **result)
    return result


@celery_app.task(name="app.workers.tasks.referrals.run_referral_qualification_checks")
def run_referral_qualification_checks(batch_size: int = 200) -> dict[str, int]:
    return asyncio.run(run_referral_qualification_checks_async(batch_size=batch_size))


@celery_app.task(name="app.workers.tasks.referrals.run_referral_reward_distribution")
def run_referral_reward_distribution(batch_size: int = 200) -> dict[str, int]:
    return asyncio.run(run_referral_reward_distribution_async(batch_size=batch_size))


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
