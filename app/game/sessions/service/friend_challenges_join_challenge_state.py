from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.models.friend_challenges import FriendChallenge
from app.game.friend_challenges.constants import (
    DUEL_STATUS_ACCEPTED,
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_LEGACY_ACTIVE,
    DUEL_STATUS_OPPONENT_DONE,
    DUEL_STATUS_PENDING,
    normalize_duel_status,
)
from app.game.sessions.errors import (
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)

from .friend_challenges_expiry import (
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)
from .friend_challenges_records import _friend_challenge_expires_at_accepted

_JOINABLE_CHALLENGE_STATUSES = frozenset(
    {
        DUEL_STATUS_PENDING,
        DUEL_STATUS_ACCEPTED,
        DUEL_STATUS_CREATOR_DONE,
        DUEL_STATUS_OPPONENT_DONE,
        DUEL_STATUS_LEGACY_ACTIVE,
    }
)


@dataclass(slots=True)
class FriendChallengeJoinState:
    challenge: FriendChallenge
    joined_now: bool


def _normalize_joinable_challenge_status(*, challenge: FriendChallenge) -> None:
    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=challenge.opponent_user_id is not None,
    )


async def _expire_joinable_challenge_if_due(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    now_utc: datetime,
) -> None:
    if not _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        return
    await _emit_friend_challenge_expired_event(
        session,
        challenge=challenge,
        happened_at=now_utc,
        source=EVENT_SOURCE_BOT,
    )


def _ensure_joinable_challenge_status(*, challenge: FriendChallenge) -> None:
    if challenge.status == "EXPIRED":
        raise FriendChallengeExpiredError
    if challenge.status not in _JOINABLE_CHALLENGE_STATUSES:
        raise FriendChallengeCompletedError


def _join_open_friend_challenge(
    *,
    challenge: FriendChallenge,
    user_id: int,
    now_utc: datetime,
) -> FriendChallengeJoinState:
    challenge.opponent_user_id = user_id
    challenge.status = DUEL_STATUS_ACCEPTED
    challenge.expires_at = _friend_challenge_expires_at_accepted(now_utc=now_utc)
    challenge.updated_at = now_utc
    return FriendChallengeJoinState(challenge=challenge, joined_now=True)


def _resolve_join_state(
    *,
    challenge: FriendChallenge,
    user_id: int,
    now_utc: datetime,
) -> FriendChallengeJoinState:
    if challenge.creator_user_id == user_id:
        return FriendChallengeJoinState(challenge=challenge, joined_now=False)
    if challenge.opponent_user_id is None:
        return _join_open_friend_challenge(
            challenge=challenge,
            user_id=user_id,
            now_utc=now_utc,
        )
    if challenge.opponent_user_id == user_id:
        return FriendChallengeJoinState(challenge=challenge, joined_now=False)
    raise FriendChallengeFullError


async def load_joinable_friend_challenge_locked(
    session: AsyncSession,
    *,
    user_id: int,
    challenge: FriendChallenge | None,
    now_utc: datetime,
) -> FriendChallengeJoinState:
    if challenge is None:
        raise FriendChallengeNotFoundError
    _normalize_joinable_challenge_status(challenge=challenge)
    await _expire_joinable_challenge_if_due(
        session,
        challenge=challenge,
        now_utc=now_utc,
    )
    _ensure_joinable_challenge_status(challenge=challenge)
    return _resolve_join_state(
        challenge=challenge,
        user_id=user_id,
        now_utc=now_utc,
    )
