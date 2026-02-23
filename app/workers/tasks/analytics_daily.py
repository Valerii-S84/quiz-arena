from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import structlog

from app.db.repo.analytics_repo import AnalyticsRepo
from app.db.session import SessionLocal
from app.economy.energy.constants import BERLIN_TIMEZONE
from app.services.analytics_daily import build_daily_snapshot
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _clamp_days_back(value: int) -> int:
    return max(1, min(14, int(value)))


async def run_analytics_daily_aggregation_async(*, days_back: int = 2) -> dict[str, object]:
    resolved_days_back = _clamp_days_back(days_back)
    now_utc = datetime.now(timezone.utc)
    berlin_today = now_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()
    processed_days: list[str] = []

    async with SessionLocal.begin() as session:
        for offset in range(resolved_days_back):
            local_day_berlin = berlin_today - timedelta(days=offset)
            snapshot = await build_daily_snapshot(
                session,
                local_date_berlin=local_day_berlin,
                now_utc=now_utc,
            )
            await AnalyticsRepo.upsert_daily(session, row=snapshot.row)
            processed_days.append(local_day_berlin.isoformat())

    result: dict[str, object] = {
        "generated_at": now_utc.isoformat(),
        "days_processed": resolved_days_back,
        "local_days_berlin": processed_days,
    }
    logger.info("analytics_daily_aggregation_finished", **result)
    return result


@celery_app.task(name="app.workers.tasks.analytics_daily.run_analytics_daily_aggregation")
def run_analytics_daily_aggregation(days_back: int = 2) -> dict[str, object]:
    return run_async_job(run_analytics_daily_aggregation_async(days_back=days_back))


celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
celery_app.conf.beat_schedule.update(
    {
        "analytics-daily-aggregation-hourly": {
            "task": "app.workers.tasks.analytics_daily.run_analytics_daily_aggregation",
            "schedule": 3600.0,
            "options": {"queue": "q_low"},
        },
    }
)
