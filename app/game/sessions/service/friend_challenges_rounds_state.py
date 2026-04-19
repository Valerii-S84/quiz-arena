from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import (
    DUEL_STATUS_EXPIRED,
    is_duel_playable_for_user,
    normalize_duel_status,
)
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)

from .friend_challenges_internal import (
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
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


async def load_friend_challenge_round_context(
    session: AsyncSession,
    *,
    challenge_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> _FriendChallengeRoundContext:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError

    has_opponent = challenge.opponent_user_id is not None
    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=has_opponent,
    )
    if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
        )
    if challenge.status == DUEL_STATUS_EXPIRED:
        raise FriendChallengeExpiredError

    is_creator = challenge.creator_user_id == user_id
    if not is_creator and challenge.opponent_user_id != user_id:
        raise FriendChallengeAccessError

    context = _FriendChallengeRoundContext(
        challenge=challenge,
        has_opponent=has_opponent,
        is_creator=is_creator,
        next_round=(
            challenge.creator_answered_round if is_creator else challenge.opponent_answered_round
        )
        + 1,
    )
    if not is_round_playable(context):
        if not has_opponent:
            raise FriendChallengeFullError
        raise FriendChallengeCompletedError
    return context
