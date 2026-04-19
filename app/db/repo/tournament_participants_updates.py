from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.tournament_participants import TournamentParticipant


async def apply_score_delta(
    session: AsyncSession,
    *,
    tournament_id: UUID,
    user_id: int,
    score_delta: Decimal,
    tie_break_delta: Decimal,
) -> int:
    stmt = (
        update(TournamentParticipant)
        .where(
            TournamentParticipant.tournament_id == tournament_id,
            TournamentParticipant.user_id == user_id,
        )
        .values(
            score=TournamentParticipant.score + score_delta,
            tie_break=TournamentParticipant.tie_break + tie_break_delta,
        )
        .returning(TournamentParticipant.user_id)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one_or_none() is not None)


async def set_score(
    session: AsyncSession,
    *,
    tournament_id: UUID,
    user_id: int,
    score: Decimal,
    tie_break: Decimal,
) -> int:
    stmt = (
        update(TournamentParticipant)
        .where(
            TournamentParticipant.tournament_id == tournament_id,
            TournamentParticipant.user_id == user_id,
        )
        .values(score=score, tie_break=tie_break)
        .returning(TournamentParticipant.user_id)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one_or_none() is not None)


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
