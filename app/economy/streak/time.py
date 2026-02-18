from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.economy.streak.constants import BERLIN_TIMEZONE


def berlin_local_date(now_utc: datetime) -> date:
    """Converts UTC datetime to Berlin local date."""
    return now_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()


def berlin_week_start(local_date: date) -> date:
    """Returns Monday date for Berlin-local calendar week."""
    return local_date - timedelta(days=local_date.weekday())
