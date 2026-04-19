from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.processed_updates import ProcessedUpdate
from app.db.repo.processed_updates_observability import (
    count_processing_older_than_seconds as count_processing_older_than_seconds_query,
)
from app.db.repo.processed_updates_observability import (
    get_processing_age_max_seconds as get_processing_age_max_seconds_query,
)
from app.db.repo.processed_updates_observability import (
    list_oldest_processing as list_oldest_processing_query,
)


class ProcessedUpdatesRepo:
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

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        update_id: int,
        status: str,
        processed_at: datetime | None = None,
        processing_task_id: str | None = None,
    ) -> ProcessedUpdate:
        processed_update = ProcessedUpdate(
            update_id=update_id,
            status=status,
            processed_at=processed_at or func.now(),
            processing_task_id=processing_task_id,
        )
        session.add(processed_update)
        await session.flush()
        return processed_update

    @staticmethod
    async def set_status(
        session: AsyncSession,
        *,
        update_id: int,
        status: str,
        processed_at: datetime | None = None,
        processing_task_id: str | None = None,
    ) -> int:
        stmt = (
            update(ProcessedUpdate)
            .where(ProcessedUpdate.update_id == update_id)
            .values(
                status=status,
                processed_at=processed_at or func.now(),
                processing_task_id=processing_task_id,
            )
            .returning(ProcessedUpdate.update_id)
        )
        result = await session.execute(stmt)
        return 1 if result.scalar_one_or_none() is not None else 0

    @staticmethod
    async def count_processing_older_than_seconds(
        session: AsyncSession,
        *,
        older_than_seconds: int,
    ) -> int:
        return await count_processing_older_than_seconds_query(
            session,
            older_than_seconds=older_than_seconds,
        )

    @staticmethod
    async def get_processing_age_max_seconds(session: AsyncSession) -> int:
        return await get_processing_age_max_seconds_query(session)

    @staticmethod
    async def list_oldest_processing(
        session: AsyncSession,
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        return await list_oldest_processing_query(session, limit=limit)

    @staticmethod
    async def delete_processed_before(
        session: AsyncSession,
        *,
        cutoff_utc: datetime,
        limit: int,
    ) -> int:
        resolved_limit = max(1, int(limit))
        candidate_ids = (
            select(ProcessedUpdate.update_id)
            .where(ProcessedUpdate.processed_at < cutoff_utc)
            .order_by(ProcessedUpdate.processed_at.asc(), ProcessedUpdate.update_id.asc())
            .limit(resolved_limit)
            .scalar_subquery()
        )
        stmt = (
            delete(ProcessedUpdate)
            .where(ProcessedUpdate.update_id.in_(candidate_ids))
            .returning(ProcessedUpdate.update_id)
        )
        result = await session.execute(stmt)
        return len(list(result.scalars()))
