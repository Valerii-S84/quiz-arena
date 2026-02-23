from datetime import datetime
from zoneinfo import ZoneInfo

from app.economy.energy.constants import BERLIN_TIMEZONE


def berlin_now(now_utc: datetime) -> datetime:
    return now_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE))


def is_weekend_flash_window(local_now: datetime) -> bool:
    weekday = local_now.weekday()  # Monday=0 ... Sunday=6
    if weekday == 4:
        return local_now.hour >= 18
    return weekday in {5, 6}
