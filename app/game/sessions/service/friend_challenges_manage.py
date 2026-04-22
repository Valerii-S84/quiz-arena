from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_manage_runtime import (
    cancel_friend_challenge_by_creator as manage_cancel_friend_challenge_by_creator,
)
from .friend_challenges_manage_runtime import (
    repost_friend_challenge_as_open as manage_repost_friend_challenge_as_open,
)


async def repost_friend_challenge_as_open(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    return await manage_repost_friend_challenge_as_open(
        session,
        user_id=user_id,
        challenge_id=challenge_id,
        now_utc=now_utc,
    )


async def cancel_friend_challenge_by_creator(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    return await manage_cancel_friend_challenge_by_creator(
        session,
        user_id=user_id,
        challenge_id=challenge_id,
        now_utc=now_utc,
    )
