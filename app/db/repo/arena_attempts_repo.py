from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt


class ArenaAttemptsRepo:
    @staticmethod
    async def get_by_id_for_update(
        session: AsyncSession,
        attempt_id: UUID,
    ) -> ArenaAttempt | None:
        stmt = select(ArenaAttempt).where(ArenaAttempt.id == attempt_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
