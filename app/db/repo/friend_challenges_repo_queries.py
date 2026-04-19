from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.friend_challenges import FriendChallenge

DUEL_LIVE_STATUSES = ("ACTIVE", "PENDING", "ACCEPTED", "CREATOR_DONE", "OPPONENT_DONE")
DUEL_JOINED_STATUSES = ("ACCEPTED", "CREATOR_DONE", "OPPONENT_DONE", "ACTIVE")


def resolved_limit(limit: int) -> int:
    return max(1, int(limit))


def for_update_due_stmt(*conditions: ColumnElement[bool], limit: int):
    return (
        select(FriendChallenge)
        .where(*conditions)
        .order_by(FriendChallenge.expires_at.asc())
        .limit(resolved_limit(limit))
        .with_for_update(skip_locked=True)
    )


async def challenge_one_or_none(session: AsyncSession, stmt) -> FriendChallenge | None:
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_challenge_rows(session: AsyncSession, stmt) -> list[FriendChallenge]:
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_challenges(session: AsyncSession, *conditions: ColumnElement[bool]) -> int:
    result = await session.execute(select(func.count(FriendChallenge.id)).where(*conditions))
    return int(result.scalar_one() or 0)
