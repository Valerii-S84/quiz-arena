from __future__ import annotations

from celery.schedules import crontab

from app.workers.tasks.daily_cup_config import (
    DAILY_CUP_CLOSE_HOUR,
    DAILY_CUP_CLOSE_MINUTE,
    DAILY_CUP_OPEN_HOUR,
    DAILY_CUP_OPEN_MINUTE,
    DAILY_CUP_ROUND_ADVANCE_SLOTS,
)


def configure_daily_cup_schedule(celery_app) -> None:
    celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
    schedule_entries = {
        "daily-cup-open-registration": {
            "task": "app.workers.tasks.daily_cup.open_registration",
            "schedule": crontab(hour=DAILY_CUP_OPEN_HOUR, minute=DAILY_CUP_OPEN_MINUTE),
            "options": {"queue": "q_normal"},
        },
        "daily-cup-close-registration": {
            "task": "app.workers.tasks.daily_cup.close_registration_and_start",
            "schedule": crontab(hour=DAILY_CUP_CLOSE_HOUR, minute=DAILY_CUP_CLOSE_MINUTE),
            "options": {"queue": "q_normal"},
        },
    }
    minute_values = {slot[1] for slot in DAILY_CUP_ROUND_ADVANCE_SLOTS}
    if len(minute_values) == 1:
        hours = ",".join(str(slot[0]) for slot in DAILY_CUP_ROUND_ADVANCE_SLOTS)
        schedule_entries["daily-cup-round-advance"] = {
            "task": "app.workers.tasks.daily_cup.advance_rounds",
            "schedule": crontab(hour=hours, minute=next(iter(minute_values))),
            "options": {"queue": "q_normal"},
        }
    else:
        for index, (hour, minute) in enumerate(DAILY_CUP_ROUND_ADVANCE_SLOTS, start=1):
            schedule_entries[f"daily-cup-round-advance-{index}"] = {
                "task": "app.workers.tasks.daily_cup.advance_rounds",
                "schedule": crontab(hour=hour, minute=minute),
                "options": {"queue": "q_normal"},
            }
    celery_app.conf.beat_schedule.update(schedule_entries)
