from __future__ import annotations

from celery.schedules import crontab

from app.workers.tasks.daily_challenge_config import (
    DAILY_PRECOMPUTE_HOUR_BERLIN,
    DAILY_PRECOMPUTE_MINUTE_BERLIN,
    DAILY_PUSH_HOUR_BERLIN,
    DAILY_PUSH_MINUTE_BERLIN,
)


def configure_daily_challenge_schedule(celery_app) -> None:
    celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
    celery_app.conf.beat_schedule.update(
        {
            "daily-question-set-precompute-berlin": {
                "task": "app.workers.tasks.daily_challenge.run_daily_question_set_precompute",
                "schedule": crontab(
                    hour=DAILY_PRECOMPUTE_HOUR_BERLIN,
                    minute=DAILY_PRECOMPUTE_MINUTE_BERLIN,
                ),
                "options": {"queue": "q_low"},
            },
            "daily-push-notifications-berlin": {
                "task": "app.workers.tasks.daily_challenge.run_daily_push_notifications",
                "schedule": crontab(
                    hour=DAILY_PUSH_HOUR_BERLIN,
                    minute=DAILY_PUSH_MINUTE_BERLIN,
                ),
                "options": {"queue": "q_low"},
            },
        }
    )
