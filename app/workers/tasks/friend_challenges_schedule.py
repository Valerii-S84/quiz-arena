from __future__ import annotations

from app.workers.tasks.friend_challenges_config import SCAN_INTERVAL_SECONDS


def configure_friend_challenges_schedule(celery_app) -> None:
    celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
    celery_app.conf.beat_schedule.update(
        {
            "friend-challenge-deadlines-every-5-minutes": {
                "task": "app.workers.tasks.friend_challenges.run_friend_challenge_deadlines",
                "schedule": float(SCAN_INTERVAL_SECONDS),
                "options": {"queue": "q_normal"},
            }
        }
    )
