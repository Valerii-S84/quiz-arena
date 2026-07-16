from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_updates import update_participant


class TournamentParticipantsRepoUpdatesMixin:
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

    @staticmethod
    async def set_standings_message_id_if_missing(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
        message_id: int,
    ) -> int:
        return await update_participant(
            session,
            tournament_id=tournament_id,
            user_id=user_id,
            values={"standings_message_id": message_id},
            extra_filters=(TournamentParticipant.standings_message_id.is_(None),),
        )

    @staticmethod
    async def set_standings_message_id(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
        message_id: int,
    ) -> int:
        return await update_participant(
            session,
            tournament_id=tournament_id,
            user_id=user_id,
            values={"standings_message_id": message_id},
        )

    @staticmethod
    async def compare_and_set_standings_message_id(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
        expected_message_id: int | None,
        message_id: int,
        expected_status: str,
        expected_round: int,
    ) -> int:
        current_message_filter = (
            TournamentParticipant.standings_message_id.is_(None)
            if expected_message_id is None
            else TournamentParticipant.standings_message_id == expected_message_id
        )
        current_generation = exists(
            select(Tournament.id).where(
                Tournament.id == tournament_id,
                Tournament.status == expected_status,
                Tournament.current_round == expected_round,
            )
        )
        return await update_participant(
            session,
            tournament_id=tournament_id,
            user_id=user_id,
            values={"standings_message_id": message_id},
            extra_filters=(current_message_filter, current_generation),
        )

    @staticmethod
    async def set_proof_card_file_id_if_missing(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
        file_id: str,
    ) -> int:
        return await update_participant(
            session,
            tournament_id=tournament_id,
            user_id=user_id,
            values={"proof_card_file_id": file_id},
            extra_filters=(TournamentParticipant.proof_card_file_id.is_(None),),
        )

    @staticmethod
    async def set_proof_card_sent(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
    ) -> int:
        return await update_participant(
            session,
            tournament_id=tournament_id,
            user_id=user_id,
            values={"proof_card_sent": True},
        )
