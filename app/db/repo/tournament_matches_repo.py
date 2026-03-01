from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_matches import TournamentMatch


class TournamentMatchesRepo:
    @staticmethod
    async def create_many(
        session: AsyncSession,
        *,
        matches: list[TournamentMatch],
    ) -> list[TournamentMatch]:
        if not matches:
            return []
        session.add_all(matches)
        await session.flush()
        return matches

    @staticmethod
    async def get_by_id_for_update(session: AsyncSession, match_id: UUID) -> TournamentMatch | None:
        stmt = select(TournamentMatch).where(TournamentMatch.id == match_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_friend_challenge_id(
        session: AsyncSession,
        *,
        friend_challenge_id: UUID,
    ) -> TournamentMatch | None:
        stmt = select(TournamentMatch).where(
            TournamentMatch.friend_challenge_id == friend_challenge_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_tournament_round(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        round_no: int,
    ) -> list[TournamentMatch]:
        stmt = (
            select(TournamentMatch)
            .where(
                TournamentMatch.tournament_id == tournament_id,
                TournamentMatch.round_no == round_no,
            )
            .order_by(TournamentMatch.deadline.asc(), TournamentMatch.id.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_tournament_for_update(
        session: AsyncSession,
        *,
        tournament_id: UUID,
    ) -> list[TournamentMatch]:
        stmt = (
            select(TournamentMatch)
            .where(TournamentMatch.tournament_id == tournament_id)
            .order_by(TournamentMatch.round_no.asc(), TournamentMatch.id.asc())
            .with_for_update()
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_tournament_round_for_update(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        round_no: int,
    ) -> list[TournamentMatch]:
        stmt = (
            select(TournamentMatch)
            .where(
                TournamentMatch.tournament_id == tournament_id,
                TournamentMatch.round_no == round_no,
            )
            .order_by(TournamentMatch.deadline.asc(), TournamentMatch.id.asc())
            .with_for_update()
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_pending_for_tournament_round(
        session: AsyncSession,
        *,
        tournament_id: UUID,
        round_no: int,
    ) -> int:
        stmt = select(func.count(TournamentMatch.id)).where(
            TournamentMatch.tournament_id == tournament_id,
            TournamentMatch.round_no == round_no,
            TournamentMatch.status == "PENDING",
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def list_pending_due_for_update(
        session: AsyncSession,
        *,
        now_utc: datetime,
        limit: int,
    ) -> list[TournamentMatch]:
        resolved_limit = max(1, int(limit))
        stmt = (
            select(TournamentMatch)
            .where(
                TournamentMatch.status == "PENDING",
                TournamentMatch.deadline <= now_utc,
            )
            .order_by(TournamentMatch.deadline.asc())
            .limit(resolved_limit)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
