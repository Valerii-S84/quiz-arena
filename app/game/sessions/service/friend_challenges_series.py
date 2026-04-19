from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_series_next_game import (
    create_friend_challenge_series_next_game as create_series_next_game_friend_challenge,
)
from .friend_challenges_series_start import (
    create_friend_challenge_best_of_three as create_series_start_friend_challenge,
)


async def create_friend_challenge_best_of_three(
    session: AsyncSession,
    *,
    initiator_user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
    best_of: int = 3,
) -> FriendChallengeSnapshot:
    return await create_series_start_friend_challenge(
        session,
        initiator_user_id=initiator_user_id,
        challenge_id=challenge_id,
        now_utc=now_utc,
        best_of=best_of,
    )


async def create_friend_challenge_series_next_game(
    session: AsyncSession,
    *,
    initiator_user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    return await create_series_next_game_friend_challenge(
        session,
        initiator_user_id=initiator_user_id,
        challenge_id=challenge_id,
        now_utc=now_utc,
    )
