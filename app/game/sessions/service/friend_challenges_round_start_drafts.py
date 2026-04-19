from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge

from .friend_challenges_round_start_question_state import load_friend_challenge_round_question_state


@dataclass(slots=True)
class FriendChallengeRoundStartDraft:
    selection_seed: str
    preferred_level: str | None
    forced_question_id: str


async def build_friend_challenge_round_start_draft(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    next_round: int,
    now_utc: datetime,
) -> FriendChallengeRoundStartDraft:
    question_state = await load_friend_challenge_round_question_state(
        session,
        challenge=challenge,
        next_round=next_round,
        now_utc=now_utc,
    )
    return FriendChallengeRoundStartDraft(
        selection_seed=question_state.selection_seed,
        preferred_level=question_state.preferred_level,
        forced_question_id=question_state.forced_question_id,
    )
