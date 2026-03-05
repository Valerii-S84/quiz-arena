from __future__ import annotations

from celery.schedules import crontab

from app.workers.tasks.daily_cup_config import (
    DAILY_CUP_CLOSE_HOUR,
    DAILY_CUP_CLOSE_MINUTE,
    DAILY_CUP_INVITE_HOUR,
    DAILY_CUP_INVITE_MINUTE,
    DAILY_CUP_LAST_CALL_REMINDER_HOUR,
    DAILY_CUP_LAST_CALL_REMINDER_MINUTE,
    DAILY_CUP_OPEN_HOUR,
    DAILY_CUP_OPEN_MINUTE,
    DAILY_CUP_PRESTART_REMINDER_HOUR,
    DAILY_CUP_PRESTART_REMINDER_MINUTE,
    DAILY_ELIMINATION_DEADLINE_HOUR,
    DAILY_ELIMINATION_DEADLINE_MINUTE,
)


def configure_daily_cup_schedule(celery_app) -> None:
    celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
    schedule_entries = {
        "daily-cup-send-invite": {
            "task": "app.workers.tasks.daily_cup.send_invite",
            "schedule": crontab(hour=DAILY_CUP_INVITE_HOUR, minute=DAILY_CUP_INVITE_MINUTE),
            "options": {"queue": "q_normal"},
        },
        "daily-cup-open-registration": {
            "task": "app.workers.tasks.daily_cup.open_registration",
            "schedule": crontab(hour=DAILY_CUP_OPEN_HOUR, minute=DAILY_CUP_OPEN_MINUTE),
            "options": {"queue": "q_normal"},
        },
        "daily-cup-last-call-reminder": {
            "task": "app.workers.tasks.daily_cup.send_last_call_reminder",
            "schedule": crontab(
                hour=DAILY_CUP_LAST_CALL_REMINDER_HOUR,
                minute=DAILY_CUP_LAST_CALL_REMINDER_MINUTE,
            ),
            "options": {"queue": "q_normal"},
        },
        "daily-cup-prestart-reminder": {
            "task": "app.workers.tasks.daily_cup.send_prestart_reminder",
            "schedule": crontab(
                hour=DAILY_CUP_PRESTART_REMINDER_HOUR,
                minute=DAILY_CUP_PRESTART_REMINDER_MINUTE,
            ),
            "options": {"queue": "q_normal"},
        },
        "daily-cup-turn-reminders": {
            "task": "app.workers.tasks.daily_cup.send_turn_reminders",
            "schedule": crontab(minute="*/10"),
            "options": {"queue": "q_normal"},
        },
        "daily-cup-close-registration": {
            "task": "app.workers.tasks.daily_cup.close_registration_and_start",
            "schedule": crontab(hour=DAILY_CUP_CLOSE_HOUR, minute=DAILY_CUP_CLOSE_MINUTE),
            "options": {"queue": "q_normal"},
        },
        "daily-elimination-final-deadline": {
            "task": "app.workers.tasks.daily_cup.final_deadline",
            "schedule": crontab(
                hour=DAILY_ELIMINATION_DEADLINE_HOUR,
                minute=DAILY_ELIMINATION_DEADLINE_MINUTE,
            ),
            "options": {"queue": "q_normal"},
        },
    }
    schedule_entries["daily-cup-round-advance"] = {
        "task": "app.workers.tasks.daily_cup.advance_rounds",
        "schedule": crontab(minute="*"),
        "options": {"queue": "q_normal"},
    }
    celery_app.conf.beat_schedule.update(schedule_entries)
