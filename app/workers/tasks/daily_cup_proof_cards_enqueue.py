from __future__ import annotations

from typing import Any

DAILY_CUP_PROOF_CARD_LOCK_SKIP_MAX_RETRIES = 3


def enqueue_daily_cup_proof_cards_job(
    *,
    tournament_id: str,
    user_id: int | None,
    delay_seconds: int,
    lock_retry_attempt: int = 0,
    celery_task: Any,
    async_fn: Any,
    is_celery_task_fn: Any,
    run_async_job_fn: Any,
    logger: Any,
) -> bool:
    if lock_retry_attempt > DAILY_CUP_PROOF_CARD_LOCK_SKIP_MAX_RETRIES:
        logger.warning(
            "daily_cup_proof_card_retry_exhausted",
            tournament_id=tournament_id,
            user_id=user_id,
            retry_attempt=lock_retry_attempt,
        )
        return False

    try:
        if is_celery_task_fn(celery_task):
            task_kwargs = {
                "tournament_id": tournament_id,
                "user_id": user_id,
                "initial_delay_seconds": 0,
            }
            if lock_retry_attempt > 0:
                task_kwargs["lock_retry_attempt"] = lock_retry_attempt
            celery_task.apply_async(
                kwargs=task_kwargs,
                countdown=max(0, int(delay_seconds)),
            )
            return True
        run_async_job_fn(
            async_fn(
                tournament_id=tournament_id,
                user_id=user_id,
                initial_delay_seconds=max(0, int(delay_seconds)),
                lock_retry_attempt=lock_retry_attempt,
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
