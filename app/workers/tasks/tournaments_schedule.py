from __future__ import annotations

from app.workers.tasks.tournaments_config import SCAN_INTERVAL_SECONDS


def configure_private_tournaments_schedule(celery_app) -> None:
    celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
    celery_app.conf.beat_schedule.update(
        {
            "private-tournaments-round-lifecycle": {
                "task": "app.workers.tasks.tournaments.run_private_tournament_rounds",
                "schedule": float(SCAN_INTERVAL_SECONDS),
                "options": {"queue": "q_normal"},
            }
        }
    )
