from __future__ import annotations

from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.tournaments_async import (
    run_private_tournament_rounds_async as _run_private_tournament_rounds_async,
)
from app.workers.tasks.tournaments_config import DEADLINE_BATCH_SIZE, ROUND_DURATION_HOURS
from app.workers.tasks.tournaments_schedule import configure_private_tournaments_schedule

run_private_tournament_rounds_async = _run_private_tournament_rounds_async

__all__ = ["run_private_tournament_rounds", "run_private_tournament_rounds_async"]


@celery_app.task(name="app.workers.tasks.tournaments.run_private_tournament_rounds")
def run_private_tournament_rounds(
    batch_size: int = DEADLINE_BATCH_SIZE,
    round_duration_hours: int = ROUND_DURATION_HOURS,
) -> dict[str, int]:
    return run_async_job(
        run_private_tournament_rounds_async(
            batch_size=batch_size,
            round_duration_hours=round_duration_hours,
        )
    )


configure_private_tournaments_schedule(celery_app)
