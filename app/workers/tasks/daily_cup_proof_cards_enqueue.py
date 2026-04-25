from __future__ import annotations

from typing import Any


def enqueue_daily_cup_proof_cards_job(
    *,
    tournament_id: str,
    user_id: int | None,
    delay_seconds: int,
    celery_task: Any,
    async_fn: Any,
    is_celery_task_fn: Any,
    run_async_job_fn: Any,
    logger: Any,
) -> bool:
    try:
        if is_celery_task_fn(celery_task):
            celery_task.apply_async(
                kwargs={
                    "tournament_id": tournament_id,
                    "user_id": user_id,
                    "initial_delay_seconds": 0,
                },
                countdown=max(0, int(delay_seconds)),
            )
            return True
        run_async_job_fn(
            async_fn(
                tournament_id=tournament_id,
                user_id=user_id,
                initial_delay_seconds=max(0, int(delay_seconds)),
            )
        )
        return True
    except Exception as exc:
        logger.warning(
            "daily_cup_proof_card_enqueue_failed",
            tournament_id=tournament_id,
            error_type=type(exc).__name__,
        )
        return False
