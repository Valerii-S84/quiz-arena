from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel

from .arena_duels_repo_models import ArenaDuelAcceptContext


class ArenaDuelsRepoAcceptMixin:
    @staticmethod
    async def get_accept_context_for_update(
        session: AsyncSession,
        *,
        duel_id: UUID,
        user_id: int,
    ) -> ArenaDuelAcceptContext | None:
        existing_context = await _get_existing_accept_context_for_update(
            session=session,
            duel_id=duel_id,
            user_id=user_id,
        )
        if existing_context is not None:
            return existing_context

        duel = await _get_duel_for_update(session, duel_id=duel_id)
        if duel is None:
            return None

        existing_attempt = await _get_existing_attempt(
            session=session,
            duel_id=duel_id,
            user_id=user_id,
        )
        return ArenaDuelAcceptContext(duel=duel, existing_attempt=existing_attempt)

    @staticmethod
    async def get_duel_for_update(
        session: AsyncSession,
        *,
        duel_id: UUID,
    ) -> ArenaDuel | None:
        return await _get_duel_for_update(session, duel_id=duel_id)

    @staticmethod
    async def get_baseline_attempt(
        session: AsyncSession,
        *,
        duel: ArenaDuel,
    ) -> ArenaAttempt | None:
        if duel.baseline_attempt_id is None:
            return None
        attempt_stmt = select(ArenaAttempt).where(
            ArenaAttempt.arena_duel_id == duel.id,
            ArenaAttempt.id == duel.baseline_attempt_id,
        )
        attempt_result = await session.execute(attempt_stmt)
        return attempt_result.scalar_one_or_none()


async def _get_existing_accept_context_for_update(
    *,
    session: AsyncSession,
    duel_id: UUID,
    user_id: int,
) -> ArenaDuelAcceptContext | None:
    stmt = (
        select(ArenaAttempt, ArenaDuel)
        .join(ArenaDuel, ArenaDuel.id == ArenaAttempt.arena_duel_id)
        .where(
            ArenaAttempt.arena_duel_id == duel_id,
            ArenaAttempt.user_id == user_id,
        )
        .with_for_update(of=(ArenaAttempt, ArenaDuel))
    )
    result = await session.execute(stmt)
    row = result.one_or_none()
    if row is None:
        return None
    attempt, duel = row.t
    return ArenaDuelAcceptContext(duel=duel, existing_attempt=attempt)


async def _get_duel_for_update(session: AsyncSession, *, duel_id: UUID) -> ArenaDuel | None:
    duel_stmt = select(ArenaDuel).where(ArenaDuel.id == duel_id).with_for_update()
    duel_result = await session.execute(duel_stmt)
    return duel_result.scalar_one_or_none()


async def _get_existing_attempt(
    *,
    session: AsyncSession,
    duel_id: UUID,
    user_id: int,
) -> ArenaAttempt | None:
    attempt_stmt = select(ArenaAttempt).where(
        ArenaAttempt.arena_duel_id == duel_id,
        ArenaAttempt.user_id == user_id,
    )
    attempt_result = await session.execute(attempt_stmt)
    return attempt_result.scalar_one_or_none()
