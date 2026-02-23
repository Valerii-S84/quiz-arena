from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.processed_updates import ProcessedUpdate


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
        processing_age_seconds = func.extract(
            "epoch",
            func.now() - ProcessedUpdate.processed_at,
        )
        stmt = select(func.count(ProcessedUpdate.update_id)).where(
            ProcessedUpdate.status == "PROCESSING",
            processing_age_seconds >= max(1, int(older_than_seconds)),
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def get_processing_age_max_seconds(session: AsyncSession) -> int:
        processing_age_seconds = func.extract(
            "epoch",
            func.now() - ProcessedUpdate.processed_at,
        )
        stmt = select(func.max(processing_age_seconds.cast(Float))).where(
            ProcessedUpdate.status == "PROCESSING",
        )
        result = await session.execute(stmt)
        raw_age = result.scalar_one_or_none()
        if raw_age is None:
            return 0
        return max(0, int(raw_age))

    @staticmethod
    async def list_oldest_processing(
        session: AsyncSession,
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        processing_age_seconds = func.extract(
            "epoch",
            func.now() - ProcessedUpdate.processed_at,
        ).cast(Float)
        stmt = (
            select(
                ProcessedUpdate.update_id,
                ProcessedUpdate.processing_task_id,
                ProcessedUpdate.processed_at,
                processing_age_seconds.label("age_seconds"),
            )
            .where(ProcessedUpdate.status == "PROCESSING")
            .order_by(processing_age_seconds.desc(), ProcessedUpdate.update_id.asc())
            .limit(max(1, int(limit)))
        )
        result = await session.execute(stmt)

        oldest: list[dict[str, object]] = []
        for update_id, processing_task_id, processed_at, age_seconds in result.all():
            oldest.append(
                {
                    "update_id": int(update_id),
                    "processing_task_id": (
                        str(processing_task_id) if processing_task_id is not None else None
                    ),
                    "processed_at": processed_at.isoformat(),
                    "age_seconds": max(0, int(age_seconds or 0)),
                }
            )
        return oldest

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
