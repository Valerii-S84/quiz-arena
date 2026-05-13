from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.analytics_repo import AnalyticsDailyUpsert, AnalyticsRepo
from app.economy.energy.constants import BERLIN_TIMEZONE
from app.services.analytics_daily_events import ANALYTICS_DAILY_EVENT_TYPES
from app.services.analytics_daily_metrics import (
    ActivityMetrics,
    build_daily_upsert,
    collect_promo_metrics,
    collect_purchase_metrics,
    collect_quiz_metrics,
)


@dataclass(frozen=True, slots=True)
class AnalyticsDailySnapshot:
    row: AnalyticsDailyUpsert
    day_start_utc: datetime
    day_end_utc: datetime


def _berlin_day_bounds_utc(local_date_berlin: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(BERLIN_TIMEZONE)
    day_start_local = datetime.combine(local_date_berlin, time.min, tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)
    return (
        day_start_local.astimezone(ZoneInfo("UTC")),
        day_end_local.astimezone(ZoneInfo("UTC")),
    )


async def _collect_activity_metrics(
    session: AsyncSession,
    *,
    day_start_utc: datetime,
    day_end_utc: datetime,
) -> ActivityMetrics:
    wau_start_utc = day_end_utc - timedelta(days=7)
    mau_start_utc = day_end_utc - timedelta(days=30)
    return ActivityMetrics(
        dau=await AnalyticsRepo.count_distinct_active_users_between(
            session,
            from_utc=day_start_utc,
            to_utc=day_end_utc,
        ),
        wau=await AnalyticsRepo.count_distinct_active_users_between(
            session,
            from_utc=wau_start_utc,
            to_utc=day_end_utc,
        ),
        mau=await AnalyticsRepo.count_distinct_active_users_between(
            session,
            from_utc=mau_start_utc,
            to_utc=day_end_utc,
        ),
    )


async def build_daily_snapshot(
    session: AsyncSession,
    *,
    local_date_berlin: date,
    now_utc: datetime,
) -> AnalyticsDailySnapshot:
    day_start_utc, day_end_utc = _berlin_day_bounds_utc(local_date_berlin)
    activity = await _collect_activity_metrics(
        session,
        day_start_utc=day_start_utc,
        day_end_utc=day_end_utc,
    )
    purchases = await collect_purchase_metrics(
        session,
        day_start_utc=day_start_utc,
        day_end_utc=day_end_utc,
    )
    promo = await collect_promo_metrics(
        session,
        day_start_utc=day_start_utc,
        day_end_utc=day_end_utc,
    )
    quiz = await collect_quiz_metrics(
        session,
        day_start_utc=day_start_utc,
        day_end_utc=day_end_utc,
    )
    event_counts = await AnalyticsRepo.count_events_by_type_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
        event_types=ANALYTICS_DAILY_EVENT_TYPES,
    )
    return AnalyticsDailySnapshot(
        row=build_daily_upsert(
            local_date_berlin=local_date_berlin,
            now_utc=now_utc,
            activity=activity,
            purchases=purchases,
            promo=promo,
            quiz=quiz,
            event_counts=event_counts,
        ),
        day_start_utc=day_start_utc,
        day_end_utc=day_end_utc,
    )
