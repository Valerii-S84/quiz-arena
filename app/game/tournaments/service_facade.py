from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.tournaments.service import (
    create_private_tournament,
    join_private_tournament_by_code,
    start_private_tournament,
)
from app.game.tournaments.types import (
    TournamentJoinResult,
    TournamentSnapshot,
    TournamentStartResult,
)


class TournamentServiceFacade:
    """Facade for tournament orchestration APIs used by bot layer."""

    @staticmethod
    async def create_private_tournament(
        session: AsyncSession,
        *,
        created_by: int,
        format_code: str,
        now_utc: datetime,
        name: str | None = None,
    ) -> TournamentSnapshot:
        return await create_private_tournament(
            session,
            created_by=created_by,
            format_code=format_code,
            now_utc=now_utc,
            name=name,
        )

    @staticmethod
    async def join_private_tournament_by_code(
        session: AsyncSession,
        *,
        user_id: int,
        invite_code: str,
        now_utc: datetime,
    ) -> TournamentJoinResult:
        return await join_private_tournament_by_code(
            session,
            user_id=user_id,
            invite_code=invite_code,
            now_utc=now_utc,
        )

    @staticmethod
    async def start_private_tournament(
        session: AsyncSession,
        *,
        creator_user_id: int,
        tournament_id: UUID,
        now_utc: datetime,
    ) -> TournamentStartResult:
        return await start_private_tournament(
            session,
            creator_user_id=creator_user_id,
            tournament_id=tournament_id,
            now_utc=now_utc,
        )
