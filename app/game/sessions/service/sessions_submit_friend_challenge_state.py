from __future__ import annotations

from dataclasses import dataclass

from app.db.models.friend_challenges import FriendChallenge


@dataclass(slots=True)
class _FriendChallengeAnswerState:
    challenge: FriendChallenge
    answered_round: int
    has_opponent: bool
    is_creator: bool
