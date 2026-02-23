from __future__ import annotations

from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.friend_challenges_async import (
    run_friend_challenge_deadlines_async as _run_friend_challenge_deadlines_async,
)
from app.workers.tasks.friend_challenges_config import DEADLINE_BATCH_SIZE
from app.workers.tasks.friend_challenges_schedule import configure_friend_challenges_schedule
from app.workers.tasks.friend_challenges_utils import (  # noqa: F401
    format_remaining_hhmm as _format_remaining_hhmm,
)

run_friend_challenge_deadlines_async = _run_friend_challenge_deadlines_async

__all__ = ["run_friend_challenge_deadlines", "run_friend_challenge_deadlines_async"]


@celery_app.task(name="app.workers.tasks.friend_challenges.run_friend_challenge_deadlines")
def run_friend_challenge_deadlines(
    batch_size: int = DEADLINE_BATCH_SIZE,
) -> dict[str, int]:
    return run_async_job(run_friend_challenge_deadlines_async(batch_size=batch_size))


configure_friend_challenges_schedule(celery_app)
