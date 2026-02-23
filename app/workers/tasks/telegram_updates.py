from __future__ import annotations

import random

from celery import Task

from app.bot.application import build_bot, build_dispatcher
from app.db.repo.processed_updates_repo import ProcessedUpdatesRepo
from app.db.session import SessionLocal
from app.services.telegram_updates import extract_update_id
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.telegram_updates_config import (
    _ACQUIRE_CREATED,
    _ACQUIRE_DUPLICATE,
    _ACQUIRE_RECLAIMED_FAILED,
    _ACQUIRE_RECLAIMED_STALE,
    EVENT_TELEGRAM_UPDATE_FAILED_FINAL,
    EVENT_TELEGRAM_UPDATE_RECLAIMED,
    EVENT_TELEGRAM_UPDATE_RETRY_SCHEDULED,
    PROCESSING_TTL_SECONDS,
    RETRY_JITTER_RATIO,
    TASK_MAX_RETRIES,
    TASK_RETRY_BACKOFF_MAX_SECONDS,
)
from app.workers.tasks.telegram_updates_processing import (
    process_update_async as _process_update_async,
)
from app.workers.tasks.telegram_updates_reliability import (
    emit_reliability_event as _emit_reliability_event,
)

process_update_async = _process_update_async

__all__ = [
    "EVENT_TELEGRAM_UPDATE_RECLAIMED",
    "PROCESSING_TTL_SECONDS",
    "ProcessedUpdatesRepo",
    "build_bot",
    "build_dispatcher",
    "process_telegram_update",
    "process_update_async",
    "random",
    "TASK_MAX_RETRIES",
    "_acquire_processing_slot",
    "_retry_backoff_seconds",
]


def _retry_backoff_seconds(
    *,
    next_retry_attempt: int,
    backoff_max_seconds: int,
) -> int:
    safe_retry_attempt = max(1, int(next_retry_attempt))
    safe_backoff_max_seconds = max(1, int(backoff_max_seconds))

    base_delay = min(
        safe_backoff_max_seconds,
        2 ** (safe_retry_attempt - 1),
    )
    max_jitter = max(0, int(base_delay * RETRY_JITTER_RATIO))
    jitter = random.randint(0, max_jitter) if max_jitter > 0 else 0
    return min(safe_backoff_max_seconds, base_delay + jitter)


async def _acquire_processing_slot(
    update_id: int,
    *,
    task_id: str | None,
    processing_ttl_seconds: int,
) -> str:
    async with SessionLocal.begin() as session:
        created = await ProcessedUpdatesRepo.try_create_processing_slot(
            session,
            update_id=update_id,
            processing_task_id=task_id,
        )
        if created:
            return _ACQUIRE_CREATED

        reclaimed_failed = await ProcessedUpdatesRepo.try_reclaim_failed_processing_slot(
            session,
            update_id=update_id,
            processing_task_id=task_id,
        )
        if reclaimed_failed:
            return _ACQUIRE_RECLAIMED_FAILED

        reclaimed_stale = await ProcessedUpdatesRepo.try_reclaim_stale_processing_slot(
            session,
            update_id=update_id,
            processing_task_id=task_id,
            processing_ttl_seconds=processing_ttl_seconds,
        )
        if reclaimed_stale:
            return _ACQUIRE_RECLAIMED_STALE

    return _ACQUIRE_DUPLICATE


@celery_app.task(
    name="app.workers.tasks.telegram_updates.process_telegram_update",
    bind=True,
    max_retries=TASK_MAX_RETRIES,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_telegram_update(
    self: Task,
    update_payload: dict[str, object],
    update_id: int | None = None,
) -> str:
    resolved_update_id = update_id if update_id is not None else extract_update_id(update_payload)
    if resolved_update_id is None:
        from app.workers.tasks.telegram_updates_processing import logger

        logger.warning("telegram_update_missing_update_id")
        return "ignored"

    task_id = str(self.request.id) if self.request.id is not None else None
    try:
        return run_async_job(
            process_update_async(
                update_payload,
                update_id=resolved_update_id,
                task_id=task_id,
            )
        )
    except Exception as exc:
        current_retries = max(0, int(getattr(self.request, "retries", 0)))
        if current_retries >= TASK_MAX_RETRIES:
            from app.workers.tasks.telegram_updates_processing import logger

            logger.exception(
                "telegram_update_failed_final",
                update_id=resolved_update_id,
                task_id=task_id,
                retries=current_retries,
                max_retries=TASK_MAX_RETRIES,
            )
            run_async_job(
                _emit_reliability_event(
                    event_type=EVENT_TELEGRAM_UPDATE_FAILED_FINAL,
                    payload={
                        "update_id": resolved_update_id,
                        "task_id": task_id,
                        "retries": current_retries,
                        "max_retries": TASK_MAX_RETRIES,
                    },
                )
            )
            raise

        next_retry_attempt = current_retries + 1
        retry_in_seconds = _retry_backoff_seconds(
            next_retry_attempt=next_retry_attempt,
            backoff_max_seconds=TASK_RETRY_BACKOFF_MAX_SECONDS,
        )
        from app.workers.tasks.telegram_updates_processing import logger

        logger.warning(
            "telegram_update_retry_scheduled",
            update_id=resolved_update_id,
            task_id=task_id,
            retry_attempt=next_retry_attempt,
            retry_in_seconds=retry_in_seconds,
            max_retries=TASK_MAX_RETRIES,
        )
        run_async_job(
            _emit_reliability_event(
                event_type=EVENT_TELEGRAM_UPDATE_RETRY_SCHEDULED,
                payload={
                    "update_id": resolved_update_id,
                    "task_id": task_id,
                    "retry_attempt": next_retry_attempt,
                    "retry_in_seconds": retry_in_seconds,
                    "max_retries": TASK_MAX_RETRIES,
                },
            )
        )
        raise self.retry(
            exc=exc,
            countdown=retry_in_seconds,
            max_retries=TASK_MAX_RETRIES,
        )
