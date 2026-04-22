from __future__ import annotations

from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.tournament_participants import TournamentParticipant


async def update_participant(
    session: AsyncSession,
    *,
    tournament_id: UUID,
    user_id: int,
    values: dict[str, object],
    extra_filters: tuple[ColumnElement[bool], ...] = (),
) -> int:
    stmt = (
        update(TournamentParticipant)
        .where(
            TournamentParticipant.tournament_id == tournament_id,
            TournamentParticipant.user_id == user_id,
            *extra_filters,
        )
        .values(**values)
        .returning(TournamentParticipant.user_id)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one_or_none() is not None)
