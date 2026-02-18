from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.processed_updates import ProcessedUpdate


class ProcessedUpdatesRepo:
    @staticmethod
    async def get_by_update_id_for_update(
        session: AsyncSession,
        *,
        update_id: int,
    ) -> ProcessedUpdate | None:
        stmt = select(ProcessedUpdate).where(ProcessedUpdate.update_id == update_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        update_id: int,
        status: str,
        processed_at: datetime,
    ) -> ProcessedUpdate:
        processed_update = ProcessedUpdate(
            update_id=update_id,
            status=status,
            processed_at=processed_at,
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
        processed_at: datetime,
    ) -> int:
        stmt = (
            update(ProcessedUpdate)
            .where(ProcessedUpdate.update_id == update_id)
            .values(status=status, processed_at=processed_at)
        )
        result = await session.execute(stmt)
        return result.rowcount or 0
