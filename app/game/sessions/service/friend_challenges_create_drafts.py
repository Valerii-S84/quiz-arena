from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge

from .friend_challenges_create_draft import FriendChallengeCreationDraft
from .friend_challenges_create_rematch_draft import (
    build_rematch_friend_challenge_draft as build_rematch_friend_challenge_draft_impl,
)
from .friend_challenges_create_standard_draft import (
    build_create_friend_challenge_draft as build_standard_friend_challenge_draft,
)


async def build_create_friend_challenge_draft(
    session: AsyncSession,
    *,
    creator_user_id: int,
    challenge_type: str,
    mode_code: str,
    total_rounds: int,
    now_utc: datetime,
) -> FriendChallengeCreationDraft:
    return await build_standard_friend_challenge_draft(
        session,
        creator_user_id=creator_user_id,
        challenge_type=challenge_type,
        mode_code=mode_code,
        total_rounds=total_rounds,
        now_utc=now_utc,
    )


async def build_rematch_friend_challenge_draft(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    initiator_user_id: int,
    opponent_user_id: int | None,
    now_utc: datetime,
) -> FriendChallengeCreationDraft:
    return await build_rematch_friend_challenge_draft_impl(
        session,
        challenge=challenge,
        initiator_user_id=initiator_user_id,
        opponent_user_id=opponent_user_id,
        now_utc=now_utc,
    )
