from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_participants import TournamentParticipant


class TournamentParticipantsRepo:
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
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

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

    @staticmethod
    async def set_standings_message_id_if_missing(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
        message_id: int,
    ) -> int:
        stmt = (
            update(TournamentParticipant)
            .where(
                TournamentParticipant.tournament_id == tournament_id,
                TournamentParticipant.user_id == user_id,
                TournamentParticipant.standings_message_id.is_(None),
            )
            .values(standings_message_id=message_id)
            .returning(TournamentParticipant.user_id)
        )
        result = await session.execute(stmt)
        return int(result.scalar_one_or_none() is not None)

    @staticmethod
    async def set_standings_message_id(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
        message_id: int,
    ) -> int:
        stmt = (
            update(TournamentParticipant)
            .where(
                TournamentParticipant.tournament_id == tournament_id,
                TournamentParticipant.user_id == user_id,
            )
            .values(standings_message_id=message_id)
            .returning(TournamentParticipant.user_id)
        )
        result = await session.execute(stmt)
        return int(result.scalar_one_or_none() is not None)

    @staticmethod
    async def set_proof_card_file_id_if_missing(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
        file_id: str,
    ) -> int:
        stmt = (
            update(TournamentParticipant)
            .where(
                TournamentParticipant.tournament_id == tournament_id,
                TournamentParticipant.user_id == user_id,
                TournamentParticipant.proof_card_file_id.is_(None),
            )
            .values(proof_card_file_id=file_id)
            .returning(TournamentParticipant.user_id)
        )
        result = await session.execute(stmt)
        return int(result.scalar_one_or_none() is not None)
