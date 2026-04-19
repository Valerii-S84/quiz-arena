from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from .friend_challenges_create_draft import FriendChallengeCreationDraft
from .friend_challenges_create_seed_state import load_friend_challenge_create_seed_state


async def build_create_friend_challenge_draft(
    session: AsyncSession,
    *,
    creator_user_id: int,
    challenge_type: str,
    mode_code: str,
    total_rounds: int,
    now_utc: datetime,
) -> FriendChallengeCreationDraft:
    seed_state = await load_friend_challenge_create_seed_state(
        session,
        creator_user_id=creator_user_id,
        mode_code=mode_code,
        total_rounds=total_rounds,
        now_utc=now_utc,
    )
    return FriendChallengeCreationDraft(
        challenge_id=seed_state.challenge_id,
        creator_user_id=creator_user_id,
        opponent_user_id=None,
        challenge_type=challenge_type,
        mode_code=mode_code,
        access_type=seed_state.access_type,
        total_rounds=total_rounds,
        question_ids=seed_state.question_ids,
        status="PENDING",
    )
