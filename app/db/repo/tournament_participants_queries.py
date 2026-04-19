from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament


async def count_for_tournament(
    session: AsyncSession,
    *,
    tournament_id: UUID,
) -> int:
    stmt = select(func.count(TournamentParticipant.user_id)).where(
        TournamentParticipant.tournament_id == tournament_id
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def list_for_tournament(
    session: AsyncSession,
    *,
    tournament_id: UUID,
) -> list[TournamentParticipant]:
    stmt = (
        select(TournamentParticipant)
        .where(TournamentParticipant.tournament_id == tournament_id)
        .order_by(
            TournamentParticipant.score.desc(),
            TournamentParticipant.tie_break.desc(),
            TournamentParticipant.joined_at.asc(),
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_for_tournament_user(
    session: AsyncSession,
    *,
    tournament_id: UUID,
    user_id: int,
) -> TournamentParticipant | None:
    stmt = select(TournamentParticipant).where(
        TournamentParticipant.tournament_id == tournament_id,
        TournamentParticipant.user_id == user_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_for_tournament_for_update(
    session: AsyncSession,
    *,
    tournament_id: UUID,
) -> list[TournamentParticipant]:
    stmt = (
        select(TournamentParticipant)
        .where(TournamentParticipant.tournament_id == tournament_id)
        .order_by(TournamentParticipant.joined_at.asc())
        .with_for_update()
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_joined_at_for_user_by_tournament_type(
    session: AsyncSession,
    *,
    user_id: int,
    tournament_type: str,
    tournament_status: str | None = None,
    limit: int = 365,
) -> list[datetime]:
    resolved_limit = max(1, min(1000, int(limit)))
    stmt = (
        select(TournamentParticipant.joined_at)
        .join(Tournament, Tournament.id == TournamentParticipant.tournament_id)
        .where(
            TournamentParticipant.user_id == user_id,
            Tournament.type == tournament_type,
        )
        .order_by(TournamentParticipant.joined_at.desc())
        .limit(resolved_limit)
    )
    if tournament_status is not None:
        stmt = stmt.where(Tournament.status == tournament_status)
    result = await session.execute(stmt)
    return list(result.scalars().all())
