from __future__ import annotations

from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.daily_challenge_async import (
    run_daily_push_notifications_async as _run_daily_push_notifications_async,
    run_daily_question_set_precompute_async as _run_daily_question_set_precompute_async,
)
from app.workers.tasks.daily_challenge_config import DAILY_PUSH_BATCH_SIZE
from app.workers.tasks.daily_challenge_schedule import configure_daily_challenge_schedule

run_daily_question_set_precompute_async = _run_daily_question_set_precompute_async
run_daily_push_notifications_async = _run_daily_push_notifications_async

__all__ = [
    "run_daily_push_notifications",
    "run_daily_push_notifications_async",
    "run_daily_question_set_precompute",
    "run_daily_question_set_precompute_async",
]


@celery_app.task(name="app.workers.tasks.daily_challenge.run_daily_question_set_precompute")
def run_daily_question_set_precompute() -> dict[str, object]:
    return run_async_job(run_daily_question_set_precompute_async())


@celery_app.task(name="app.workers.tasks.daily_challenge.run_daily_push_notifications")
def run_daily_push_notifications(batch_size: int = DAILY_PUSH_BATCH_SIZE) -> dict[str, object]:
    return run_async_job(run_daily_push_notifications_async(batch_size=batch_size))


configure_daily_challenge_schedule(celery_app)
