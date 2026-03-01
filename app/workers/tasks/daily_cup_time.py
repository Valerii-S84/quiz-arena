from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.workers.tasks.daily_cup_config import (
    DAILY_CUP_CLOSE_HOUR,
    DAILY_CUP_CLOSE_MINUTE,
    DAILY_CUP_OPEN_HOUR,
    DAILY_CUP_OPEN_MINUTE,
    DAILY_CUP_TIMEZONE,
)


@dataclass(frozen=True, slots=True)
class DailyCupWindow:
    berlin_date: date
    open_at_utc: datetime
    close_at_utc: datetime


def get_daily_cup_window(*, now_utc: datetime) -> DailyCupWindow:
    tz = ZoneInfo(DAILY_CUP_TIMEZONE)
    local_now = now_utc.astimezone(tz)
    local_date = local_now.date()
    open_local = datetime(
        local_date.year,
        local_date.month,
        local_date.day,
        DAILY_CUP_OPEN_HOUR,
        DAILY_CUP_OPEN_MINUTE,
        tzinfo=tz,
    )
    close_local = datetime(
        local_date.year,
        local_date.month,
        local_date.day,
        DAILY_CUP_CLOSE_HOUR,
        DAILY_CUP_CLOSE_MINUTE,
        tzinfo=tz,
    )
    return DailyCupWindow(
        berlin_date=local_date,
        open_at_utc=open_local.astimezone(timezone.utc),
        close_at_utc=close_local.astimezone(timezone.utc),
    )


def format_close_time_local(*, close_at_utc: datetime) -> str:
    return close_at_utc.astimezone(ZoneInfo(DAILY_CUP_TIMEZONE)).strftime("%H:%M")
