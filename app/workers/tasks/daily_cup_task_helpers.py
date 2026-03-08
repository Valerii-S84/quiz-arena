from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def is_celery_task(task_obj: object) -> bool:
    return type(task_obj).__module__.startswith("celery.")


def is_today_daily_cup_tournament(
    *,
    registration_deadline: datetime,
    now_utc: datetime,
    timezone_name: str,
) -> bool:
    tz = ZoneInfo(timezone_name)
    return registration_deadline.astimezone(tz).date() == now_utc.astimezone(tz).date()
