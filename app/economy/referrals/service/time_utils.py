from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.economy.energy.constants import BERLIN_TIMEZONE


def _berlin_datetime(now_utc: datetime) -> datetime:
    return now_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE))


def _berlin_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local_now = _berlin_datetime(now_utc)
    local_day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_day_end = local_day_start + timedelta(days=1)
    return (
        local_day_start.astimezone(now_utc.tzinfo),
        local_day_end.astimezone(now_utc.tzinfo),
    )


def _berlin_month_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local_now = _berlin_datetime(now_utc)
    local_month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if local_month_start.month == 12:
        local_next_month = local_month_start.replace(year=local_month_start.year + 1, month=1)
    else:
        local_next_month = local_month_start.replace(month=local_month_start.month + 1)
    return (
        local_month_start.astimezone(now_utc.tzinfo),
        local_next_month.astimezone(now_utc.tzinfo),
    )
