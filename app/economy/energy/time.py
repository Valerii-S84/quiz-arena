from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.economy.energy.constants import BERLIN_TIMEZONE


def berlin_local_date(now_utc: datetime) -> date:
    """Converts UTC datetime to Berlin local date for daily boundaries."""
    return now_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()


def regen_ticks(last_regen_at: datetime, now_utc: datetime, regen_interval_sec: int) -> int:
    """Returns number of full regen intervals elapsed since last tick."""
    elapsed_seconds = int((now_utc - last_regen_at).total_seconds())
    if elapsed_seconds <= 0:
        return 0
    return elapsed_seconds // regen_interval_sec
