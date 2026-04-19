from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.game.friend_challenges.constants import is_duel_playable_for_user
from app.game.sessions.errors import FriendChallengeCompletedError, FriendChallengeFullError

from .friend_challenges_round_challenge_state import (
    FriendChallengeRoundChallengeState,
    load_round_friend_challenge,
)


@dataclass(slots=True)
class _FriendChallengeRoundContext:
    challenge: FriendChallenge
    has_opponent: bool
    is_creator: bool
    next_round: int


def is_round_playable(context: _FriendChallengeRoundContext) -> bool:
    return is_duel_playable_for_user(
        status=context.challenge.status,
        has_opponent=context.has_opponent,
        is_creator=context.is_creator,
    )


def _build_round_context(
    challenge_state: FriendChallengeRoundChallengeState,
) -> _FriendChallengeRoundContext:
    context = _FriendChallengeRoundContext(
        challenge=challenge_state.challenge,
        has_opponent=challenge_state.has_opponent,
        is_creator=challenge_state.is_creator,
        next_round=(
            challenge_state.challenge.creator_answered_round
            if challenge_state.is_creator
            else challenge_state.challenge.opponent_answered_round
        )
        + 1,
    )
    return context


async def load_friend_challenge_round_context(
    session: AsyncSession,
    *,
    challenge_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> _FriendChallengeRoundContext:
    challenge_state = await load_round_friend_challenge(
        session,
        challenge_id=challenge_id,
        user_id=user_id,
        now_utc=now_utc,
    )
    context = _build_round_context(challenge_state)
    if not is_round_playable(context):
        if not challenge_state.has_opponent:
            raise FriendChallengeFullError
        raise FriendChallengeCompletedError
    return context
