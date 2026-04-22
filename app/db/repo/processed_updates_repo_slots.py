from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.processed_updates import ProcessedUpdate


class ProcessedUpdatesRepoSlotsMixin:
    @staticmethod
    async def get_by_update_id_for_update(
        session: AsyncSession,
        *,
        update_id: int,
    ) -> ProcessedUpdate | None:
        stmt = (
            select(ProcessedUpdate).where(ProcessedUpdate.update_id == update_id).with_for_update()
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def try_create_processing_slot(
        session: AsyncSession,
        *,
        update_id: int,
        processing_task_id: str | None,
    ) -> bool:
        stmt = (
            postgresql_insert(ProcessedUpdate)
            .values(
                update_id=update_id,
                status="PROCESSING",
                processed_at=func.now(),
                processing_task_id=processing_task_id,
            )
            .on_conflict_do_nothing(index_elements=[ProcessedUpdate.update_id])
            .returning(ProcessedUpdate.update_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def try_reclaim_failed_processing_slot(
        session: AsyncSession,
        *,
        update_id: int,
        processing_task_id: str | None,
    ) -> bool:
        stmt = (
            update(ProcessedUpdate)
            .where(
                ProcessedUpdate.update_id == update_id,
                ProcessedUpdate.status == "FAILED",
            )
            .values(
                status="PROCESSING",
                processed_at=func.now(),
                processing_task_id=processing_task_id,
            )
            .returning(ProcessedUpdate.update_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def try_reclaim_stale_processing_slot(
        session: AsyncSession,
        *,
        update_id: int,
        processing_task_id: str | None,
        processing_ttl_seconds: int,
    ) -> bool:
        processing_age_seconds = func.extract(
            "epoch",
            func.now() - ProcessedUpdate.processed_at,
        )
        stmt = (
            update(ProcessedUpdate)
            .where(
                ProcessedUpdate.update_id == update_id,
                ProcessedUpdate.status == "PROCESSING",
                processing_age_seconds >= max(1, int(processing_ttl_seconds)),
            )
            .values(
                status="PROCESSING",
                processed_at=func.now(),
                processing_task_id=processing_task_id,
            )
            .returning(ProcessedUpdate.update_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None
