from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.workers.tasks import daily_cup_config


def is_daily_cup_enabled() -> bool:
    return daily_cup_config.DAILY_CUP_ENABLED


def disabled_daily_cup_task_result() -> dict[str, int]:
    return {"processed": 0, "disabled": 1}


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
