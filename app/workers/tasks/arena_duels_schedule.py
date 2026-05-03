from __future__ import annotations

ARENA_DUEL_EXPIRY_SCAN_INTERVAL_SECONDS = 300


def configure_arena_duels_schedule(celery_app) -> None:
    celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
    celery_app.conf.beat_schedule.update(
        {
            "arena-duel-expiry-every-5-minutes": {
                "task": "app.workers.tasks.arena_duels.expire_arena_duels",
                "schedule": float(ARENA_DUEL_EXPIRY_SCAN_INTERVAL_SECONDS),
                "options": {"queue": "q_normal"},
            }
        }
    )
