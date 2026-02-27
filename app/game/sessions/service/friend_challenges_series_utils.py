from __future__ import annotations

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.errors import FriendChallengeAccessError


def _series_wins_needed(*, best_of: int) -> int:
    resolved_best_of = max(1, int(best_of))
    return (resolved_best_of // 2) + 1


def _count_series_wins(
    *,
    series_challenges: list[FriendChallenge],
    creator_user_id: int,
    opponent_user_id: int | None,
) -> tuple[int, int]:
    creator_wins = 0
    opponent_wins = 0
    for item in series_challenges:
        if item.status not in {"COMPLETED", "EXPIRED", "WALKOVER"}:
            continue
        if item.winner_user_id == creator_user_id:
            creator_wins += 1
        elif opponent_user_id is not None and item.winner_user_id == opponent_user_id:
            opponent_wins += 1
    return creator_wins, opponent_wins


def _resolve_challenge_opponent_user_id(
    *,
    challenge: FriendChallenge,
    initiator_user_id: int,
) -> int:
    if challenge.creator_user_id == initiator_user_id:
        opponent_user_id = challenge.opponent_user_id
    else:
        opponent_user_id = challenge.creator_user_id
    if opponent_user_id is None:
        raise FriendChallengeAccessError
    return opponent_user_id
