from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament


class TournamentParticipantsRepoQueriesMixin:
    @staticmethod
    async def create_once(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
        joined_at: datetime,
    ) -> bool:
        stmt = (
            insert(TournamentParticipant)
            .values(
                tournament_id=tournament_id,
                user_id=user_id,
                score=Decimal("0"),
                tie_break=Decimal("0"),
                joined_at=joined_at,
                standings_message_id=None,
                proof_card_file_id=None,
                proof_card_sent=False,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    TournamentParticipant.tournament_id,
                    TournamentParticipant.user_id,
                ]
            )
            .returning(TournamentParticipant.user_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def count_for_tournament(session: AsyncSession, *, tournament_id: UUID) -> int:
        stmt = select(func.count(TournamentParticipant.user_id)).where(
            TournamentParticipant.tournament_id == tournament_id
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
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
                TournamentParticipant.user_id.asc(),
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
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

    @staticmethod
    async def get_for_tournament_user_for_update(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
        skip_locked: bool = False,
    ) -> TournamentParticipant | None:
        stmt = (
            select(TournamentParticipant)
            .where(
                TournamentParticipant.tournament_id == tournament_id,
                TournamentParticipant.user_id == user_id,
            )
            .with_for_update(skip_locked=skip_locked)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
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

    @staticmethod
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
