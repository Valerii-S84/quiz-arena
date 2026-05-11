from __future__ import annotations

from app.db.models.friend_challenges import FriendChallenge
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.friend_challenges.constants import (
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_PENDING,
    DUEL_TYPE_DIRECT,
)
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeArenaPublishBaselineRequiredError,
)


def ensure_friend_challenge_can_publish_to_arena(
    *,
    challenge: FriendChallenge,
    user_id: int,
) -> None:
    if challenge.creator_user_id != user_id:
        raise FriendChallengeAccessError
    if challenge.opponent_user_id is not None:
        raise FriendChallengeAccessError
    if challenge.challenge_type != DUEL_TYPE_DIRECT:
        raise FriendChallengeAccessError
    if int(challenge.total_rounds) != DUEL_QUESTION_COUNT:
        raise FriendChallengeAccessError
    if challenge.status not in {DUEL_STATUS_PENDING, DUEL_STATUS_CREATOR_DONE}:
        raise FriendChallengeAccessError
    if challenge.tournament_match_id is not None:
        raise FriendChallengeAccessError


def ensure_friend_creator_baseline_publishable(challenge: FriendChallenge) -> None:
    if friend_creator_baseline_needs_play(challenge):
        raise FriendChallengeArenaPublishBaselineRequiredError
    if not friend_creator_baseline_is_ready(challenge):
        raise FriendChallengeAccessError


def friend_creator_baseline_is_ready(challenge: FriendChallenge) -> bool:
    return (
        int(challenge.total_rounds) == DUEL_QUESTION_COUNT
        and int(challenge.creator_answered_round) >= DUEL_QUESTION_COUNT
        and challenge.creator_finished_at is not None
    )


def friend_creator_baseline_needs_play(challenge: FriendChallenge) -> bool:
    return (
        challenge.status == DUEL_STATUS_PENDING
        and int(challenge.creator_answered_round) < DUEL_QUESTION_COUNT
        and challenge.creator_finished_at is None
    )
