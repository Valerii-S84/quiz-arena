from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_participants import TournamentParticipant
from app.db.repo.tournament_participants_queries import (
    count_for_tournament as count_for_tournament_query,
)
from app.db.repo.tournament_participants_queries import (
    get_for_tournament_user as get_for_tournament_user_query,
)
from app.db.repo.tournament_participants_queries import (
    list_for_tournament as list_for_tournament_query,
)
from app.db.repo.tournament_participants_queries import (
    list_for_tournament_for_update as list_for_tournament_for_update_query,
)
from app.db.repo.tournament_participants_queries import (
    list_joined_at_for_user_by_tournament_type as list_joined_at_for_user_by_tournament_type_query,
)
from app.db.repo.tournament_participants_updates import apply_score_delta as apply_score_delta_query
from app.db.repo.tournament_participants_updates import set_score as set_score_query
from app.db.repo.tournament_participants_updates import update_participant


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
        return await count_for_tournament_query(
            session,
            tournament_id=tournament_id,
        )

    @staticmethod
    async def list_for_tournament(
        session: AsyncSession,
        *,
        tournament_id: UUID,
    ) -> list[TournamentParticipant]:
        return await list_for_tournament_query(
            session,
            tournament_id=tournament_id,
        )

    @staticmethod
    async def get_for_tournament_user(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
    ) -> TournamentParticipant | None:
        return await get_for_tournament_user_query(
            session,
            tournament_id=tournament_id,
            user_id=user_id,
        )

    @staticmethod
    async def list_for_tournament_for_update(
        session: AsyncSession,
        *,
        tournament_id: UUID,
    ) -> list[TournamentParticipant]:
        return await list_for_tournament_for_update_query(
            session,
            tournament_id=tournament_id,
        )

    @staticmethod
    async def apply_score_delta(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
        score_delta: Decimal,
        tie_break_delta: Decimal,
    ) -> int:
        return await apply_score_delta_query(
            session,
            tournament_id=tournament_id,
            user_id=user_id,
            score_delta=score_delta,
            tie_break_delta=tie_break_delta,
        )

    @staticmethod
    async def set_score(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        user_id: int,
        score: Decimal,
        tie_break: Decimal,
    ) -> int:
        return await set_score_query(
            session,
            tournament_id=tournament_id,
            user_id=user_id,
            score=score,
            tie_break=tie_break,
        )

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

    @staticmethod
    async def list_joined_at_for_user_by_tournament_type(
        session: AsyncSession,
        *,
        user_id: int,
        tournament_type: str,
        tournament_status: str | None = None,
        limit: int = 365,
    ) -> list[datetime]:
        return await list_joined_at_for_user_by_tournament_type_query(
            session,
            user_id=user_id,
            tournament_type=tournament_type,
            tournament_status=tournament_status,
            limit=limit,
        )
