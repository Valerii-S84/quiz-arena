from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournaments import Tournament


class TournamentsRepo:
    @staticmethod
    async def create(session: AsyncSession, *, tournament: Tournament) -> Tournament:
        session.add(tournament)
        await session.flush()
        return tournament

    @staticmethod
    async def get_by_id(session: AsyncSession, tournament_id: UUID) -> Tournament | None:
        return await session.get(Tournament, tournament_id)

    @staticmethod
    async def get_by_id_for_update(session: AsyncSession, tournament_id: UUID) -> Tournament | None:
        stmt = select(Tournament).where(Tournament.id == tournament_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_invite_code(session: AsyncSession, invite_code: str) -> Tournament | None:
        stmt = select(Tournament).where(Tournament.invite_code == invite_code)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_invite_code_for_update(
        session: AsyncSession,
        invite_code: str,
    ) -> Tournament | None:
        stmt = select(Tournament).where(Tournament.invite_code == invite_code).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_due_registration_close_for_update(
        session: AsyncSession,
        *,
        now_utc: datetime,
        limit: int,
    ) -> list[Tournament]:
        resolved_limit = max(1, int(limit))
        stmt = (
            select(Tournament)
            .where(
                Tournament.status == "REGISTRATION",
                Tournament.registration_deadline <= now_utc,
            )
            .order_by(Tournament.registration_deadline.asc())
            .limit(resolved_limit)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_due_round_deadline_for_update(
        session: AsyncSession,
        *,
        now_utc: datetime,
        limit: int,
    ) -> list[Tournament]:
        resolved_limit = max(1, int(limit))
        stmt = (
            select(Tournament)
            .where(
                Tournament.status.in_(("ROUND_1", "ROUND_2", "ROUND_3")),
                Tournament.round_deadline.is_not(None),
                Tournament.round_deadline <= now_utc,
            )
            .order_by(Tournament.round_deadline.asc())
            .limit(resolved_limit)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
