from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from aiogram.types import Update
from sqlalchemy.exc import IntegrityError

from app.bot.application import build_bot, build_dispatcher
from app.db.repo.processed_updates_repo import ProcessedUpdatesRepo
from app.db.session import SessionLocal
from app.services.telegram_updates import extract_update_id
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _acquire_processing_slot(update_id: int, *, now_utc: datetime) -> bool:
    try:
        async with SessionLocal.begin() as session:
            await ProcessedUpdatesRepo.create(
                session,
                update_id=update_id,
                status="PROCESSING",
                processed_at=now_utc,
            )
        return True
    except IntegrityError:
        async with SessionLocal.begin() as session:
            processed_update = await ProcessedUpdatesRepo.get_by_update_id_for_update(
                session,
                update_id=update_id,
            )
            if processed_update is None:
                return False

            if processed_update.status in {"PROCESSING", "PROCESSED"}:
                return False

            processed_update.status = "PROCESSING"
            processed_update.processed_at = now_utc
        return True


async def process_update_async(update_payload: dict[str, object], *, update_id: int) -> str:
    now_utc = datetime.now(timezone.utc)
    should_process = await _acquire_processing_slot(update_id, now_utc=now_utc)
    if not should_process:
        logger.info("telegram_update_duplicate", update_id=update_id)
        return "duplicate"

    bot = build_bot()
    dispatcher = build_dispatcher()

    try:
        update = Update.model_validate(update_payload)
        await dispatcher.feed_update(bot, update)
    except Exception:
        failed_at = datetime.now(timezone.utc)
        async with SessionLocal.begin() as session:
            await ProcessedUpdatesRepo.set_status(
                session,
                update_id=update_id,
                status="FAILED",
                processed_at=failed_at,
            )
        logger.exception("telegram_update_processing_failed", update_id=update_id)
        raise
    finally:
        await bot.session.close()

    completed_at = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        await ProcessedUpdatesRepo.set_status(
            session,
            update_id=update_id,
            status="PROCESSED",
            processed_at=completed_at,
        )

    logger.info("telegram_update_processed", update_id=update_id)
    return "processed"


@celery_app.task(name="app.workers.tasks.telegram_updates.process_telegram_update")
def process_telegram_update(update_payload: dict[str, object], update_id: int | None = None) -> str:
    resolved_update_id = update_id if update_id is not None else extract_update_id(update_payload)
    if resolved_update_id is None:
        logger.warning("telegram_update_missing_update_id")
        return "ignored"

    return asyncio.run(process_update_async(update_payload, update_id=resolved_update_id))
