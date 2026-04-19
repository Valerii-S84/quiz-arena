from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.friend_challenges.constants import DUEL_TYPE_DIRECT
from app.game.sessions.types import FriendChallengeSnapshot

from .constants import FRIEND_CHALLENGE_TOTAL_ROUNDS
from .friend_challenges_create_rematch import (
    create_friend_challenge_rematch as create_rematch_friend_challenge,
)
from .friend_challenges_create_standard import (
    create_friend_challenge as create_standard_friend_challenge,
)


async def create_friend_challenge(
    session: AsyncSession,
    *,
    creator_user_id: int,
    mode_code: str,
    now_utc: datetime,
    challenge_type: str = DUEL_TYPE_DIRECT,
    total_rounds: int = FRIEND_CHALLENGE_TOTAL_ROUNDS,
) -> FriendChallengeSnapshot:
    return await create_standard_friend_challenge(
        session,
        creator_user_id=creator_user_id,
        mode_code=mode_code,
        now_utc=now_utc,
        challenge_type=challenge_type,
        total_rounds=total_rounds,
    )


async def create_friend_challenge_rematch(
    session: AsyncSession,
    *,
    initiator_user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    return await create_rematch_friend_challenge(
        session,
        initiator_user_id=initiator_user_id,
        challenge_id=challenge_id,
        now_utc=now_utc,
    )
