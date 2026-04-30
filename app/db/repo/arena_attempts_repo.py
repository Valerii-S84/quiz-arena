from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel


@dataclass(frozen=True, slots=True)
class ArenaAttemptStartContext:
    attempt: ArenaAttempt
    duel: ArenaDuel


class ArenaAttemptsRepo:
    @staticmethod
    async def get_by_id_for_update(
        session: AsyncSession,
        attempt_id: UUID,
    ) -> ArenaAttempt | None:
        stmt = select(ArenaAttempt).where(ArenaAttempt.id == attempt_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_start_context_for_update(
        session: AsyncSession,
        attempt_id: UUID,
    ) -> ArenaAttemptStartContext | None:
        stmt = (
            select(ArenaAttempt, ArenaDuel)
            .join(ArenaDuel, ArenaDuel.id == ArenaAttempt.arena_duel_id)
            .where(ArenaAttempt.id == attempt_id)
            .with_for_update(of=(ArenaAttempt, ArenaDuel))
        )
        result = await session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None
        attempt, duel = row.t
        return ArenaAttemptStartContext(attempt=attempt, duel=duel)
