from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from .friend_challenges_access import _resolve_friend_challenge_access_type
from .friend_challenges_question_plan import select_duel_question_ids


@dataclass(slots=True)
class FriendChallengeCreateSeedState:
    challenge_id: UUID
    access_type: str
    question_ids: list[str]


async def load_friend_challenge_create_seed_state(
    session: AsyncSession,
    *,
    creator_user_id: int,
    mode_code: str,
    total_rounds: int,
    now_utc: datetime,
) -> FriendChallengeCreateSeedState:
    access_type = await _resolve_friend_challenge_access_type(
        session,
        creator_user_id=creator_user_id,
        now_utc=now_utc,
    )
    challenge_id = uuid4()
    question_ids = await select_duel_question_ids(
        session,
        mode_code=mode_code,
        total_rounds=total_rounds,
        now_utc=now_utc,
        challenge_seed=str(challenge_id),
    )
    return FriendChallengeCreateSeedState(
        challenge_id=challenge_id,
        access_type=access_type,
        question_ids=question_ids,
    )
