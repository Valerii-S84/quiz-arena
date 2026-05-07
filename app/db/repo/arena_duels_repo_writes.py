from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_ROLE_CHALLENGER,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_DUEL_STATUS_DRAFT,
    ARENA_DUEL_STATUS_EXPIRED,
)

from .arena_duels_repo_models import ArenaActiveDuelRow


class ArenaDuelsRepoWritesMixin:
    @staticmethod
    async def create_duel(session: AsyncSession, *, duel: ArenaDuel) -> ArenaDuel:
        session.add(duel)
        await session.flush()
        return duel

    @staticmethod
    async def create_attempt(session: AsyncSession, *, attempt: ArenaAttempt) -> ArenaAttempt:
        session.add(attempt)
        await session.flush()
        return attempt

    @staticmethod
    async def get_source_friend_duel_with_baseline_for_update(
        session: AsyncSession,
        *,
        source_friend_challenge_id: UUID,
    ) -> ArenaActiveDuelRow | None:
        stmt = (
            select(ArenaDuel, ArenaAttempt)
            .join(
                ArenaAttempt,
                and_(
                    ArenaAttempt.arena_duel_id == ArenaDuel.id,
                    ArenaAttempt.id == ArenaDuel.baseline_attempt_id,
                ),
            )
            .where(ArenaDuel.source_friend_challenge_id == source_friend_challenge_id)
            .where(
                ArenaAttempt.score.is_not(None),
                ArenaAttempt.time_ms.is_not(None),
                ArenaAttempt.completed_at.is_not(None),
            )
            .order_by(ArenaDuel.created_at.desc(), ArenaDuel.id.desc())
            .limit(1)
            .with_for_update(of=(ArenaDuel, ArenaAttempt))
        )
        result = await session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None
        duel, baseline_attempt = row.t
        return ArenaActiveDuelRow(duel=duel, baseline_attempt=baseline_attempt)

    @staticmethod
    async def expire_active_duels(session: AsyncSession, *, now_utc: datetime) -> int:
        return await _expire_duels_by_status(
            session=session,
            status=ARENA_DUEL_STATUS_ACTIVE,
            now_utc=now_utc,
        )

    @staticmethod
    async def expire_draft_duels(session: AsyncSession, *, now_utc: datetime) -> int:
        return await _expire_duels_by_status(
            session=session,
            status=ARENA_DUEL_STATUS_DRAFT,
            now_utc=now_utc,
        )

    @staticmethod
    async def count_creator_duels_by_access_type(
        session: AsyncSession,
        *,
        creator_user_id: int,
        access_type: str,
        since: datetime | None = None,
    ) -> int:
        stmt = select(func.count(ArenaDuel.id)).where(
            ArenaDuel.creator_user_id == creator_user_id,
            ArenaDuel.access_type == access_type,
            ArenaDuel.source_friend_challenge_id.is_(None),
        )
        if since is not None:
            stmt = stmt.where(ArenaDuel.created_at >= since)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_challenger_attempts_by_access_type(
        session: AsyncSession,
        *,
        user_id: int,
        access_type: str,
        since: datetime | None = None,
    ) -> int:
        stmt = select(func.count(ArenaAttempt.id)).where(
            ArenaAttempt.user_id == user_id,
            ArenaAttempt.role == ARENA_ATTEMPT_ROLE_CHALLENGER,
            ArenaAttempt.access_type == access_type,
        )
        if since is not None:
            stmt = stmt.where(ArenaAttempt.created_at >= since)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_paid_ticket_usage(session: AsyncSession, *, user_id: int) -> int:
        duel_result = await session.execute(
            select(func.count(ArenaDuel.id)).where(
                ArenaDuel.creator_user_id == user_id,
                ArenaDuel.access_type == "PAID_TICKET",
                ArenaDuel.source_friend_challenge_id.is_(None),
            )
        )
        attempt_result = await session.execute(
            select(func.count(ArenaAttempt.id)).where(
                ArenaAttempt.user_id == user_id,
                ArenaAttempt.role == ARENA_ATTEMPT_ROLE_CHALLENGER,
                ArenaAttempt.access_type == "PAID_TICKET",
            )
        )
        return int(duel_result.scalar_one() or 0) + int(attempt_result.scalar_one() or 0)


async def _expire_duels_by_status(
    *,
    session: AsyncSession,
    status: str,
    now_utc: datetime,
) -> int:
    stmt = (
        update(ArenaDuel)
        .where(
            ArenaDuel.status == status,
            ArenaDuel.expires_at <= now_utc,
        )
        .values(status=ARENA_DUEL_STATUS_EXPIRED, updated_at=now_utc)
    )
    result = await session.execute(stmt)
    return int(getattr(result, "rowcount", 0) or 0)
