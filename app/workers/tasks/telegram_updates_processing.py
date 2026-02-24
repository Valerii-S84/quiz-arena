from __future__ import annotations

import structlog
from aiogram.types import Update

from app.db.repo.processed_updates_repo import ProcessedUpdatesRepo
from app.db.session import SessionLocal
from app.workers.tasks.telegram_updates_config import (
    _ACQUIRE_CREATED,
    _ACQUIRE_DUPLICATE,
    _ACQUIRE_RECLAIMED_FAILED,
    _ACQUIRE_RECLAIMED_STALE,
    EVENT_TELEGRAM_UPDATE_RECLAIMED,
    PROCESSING_TTL_SECONDS,
)
from app.workers.tasks.telegram_updates_reliability import emit_reliability_event

logger = structlog.get_logger("app.workers.tasks.telegram_updates")


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


async def process_update_async(
    update_payload: dict[str, object],
    *,
    update_id: int,
    task_id: str | None = None,
) -> str:
    acquire_outcome = await _acquire_processing_slot(
        update_id,
        task_id=task_id,
        processing_ttl_seconds=PROCESSING_TTL_SECONDS,
    )
    if acquire_outcome == _ACQUIRE_DUPLICATE:
        logger.info("telegram_update_duplicate", update_id=update_id)
        return "duplicate"

    if acquire_outcome == _ACQUIRE_RECLAIMED_STALE:
        logger.warning(
            "telegram_update_processing_reclaimed_stale",
            update_id=update_id,
            processing_ttl_seconds=PROCESSING_TTL_SECONDS,
        )
        await emit_reliability_event(
            event_type=EVENT_TELEGRAM_UPDATE_RECLAIMED,
            payload={
                "update_id": update_id,
                "task_id": task_id,
                "processing_ttl_seconds": PROCESSING_TTL_SECONDS,
            },
        )
    elif acquire_outcome == _ACQUIRE_RECLAIMED_FAILED:
        logger.info("telegram_update_processing_reclaimed_failed", update_id=update_id)

    from app.workers.tasks import telegram_updates as telegram_updates_tasks

    bot = telegram_updates_tasks.build_bot()
    dispatcher = telegram_updates_tasks.build_dispatcher()

    try:
        update = Update.model_validate(update_payload)
        await dispatcher.feed_update(bot, update)
    except Exception:
        async with SessionLocal.begin() as session:
            await ProcessedUpdatesRepo.set_status(
                session,
                update_id=update_id,
                status="FAILED",
                processing_task_id=None,
            )
        logger.exception("telegram_update_processing_failed", update_id=update_id)
        raise
    finally:
        await bot.session.close()

    async with SessionLocal.begin() as session:
        await ProcessedUpdatesRepo.set_status(
            session,
            update_id=update_id,
            status="PROCESSED",
            processing_task_id=None,
        )

    logger.info("telegram_update_processed", update_id=update_id)
    return "processed"
