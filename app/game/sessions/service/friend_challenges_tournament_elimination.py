from __future__ import annotations

import random
from datetime import datetime

from app.db.models.friend_challenges import FriendChallenge
from app.db.models.tournament_matches import TournamentMatch


def _score_for_user(*, challenge: FriendChallenge, user_id: int) -> int:
    if int(challenge.creator_user_id) == int(user_id):
        return int(challenge.creator_score)
    return int(challenge.opponent_score)


def _finished_at_for_user(*, challenge: FriendChallenge, user_id: int) -> datetime | None:
    if int(challenge.creator_user_id) == int(user_id):
        return challenge.creator_finished_at
    return challenge.opponent_finished_at


def ensure_elimination_winner(
    *,
    challenge: FriendChallenge,
    match: TournamentMatch,
) -> tuple[int, int | None]:
    user_a = int(match.user_a)
    user_b = int(match.user_b) if match.user_b is not None else None
    if user_b is None:
        challenge.winner_user_id = user_a
        return user_a, None
    score_a = _score_for_user(challenge=challenge, user_id=user_a)
    score_b = _score_for_user(challenge=challenge, user_id=user_b)
    if score_a > score_b:
        challenge.winner_user_id = user_a
        return user_a, user_b
    if score_b > score_a:
        challenge.winner_user_id = user_b
        return user_b, user_a
    finished_a = _finished_at_for_user(challenge=challenge, user_id=user_a)
    finished_b = _finished_at_for_user(challenge=challenge, user_id=user_b)
    if finished_a is not None and finished_b is not None and finished_a != finished_b:
        winner_id = user_a if finished_a < finished_b else user_b
        loser_id = user_b if winner_id == user_a else user_a
        challenge.winner_user_id = winner_id
        return winner_id, loser_id
    winner_id = random.choice((user_a, user_b))
    loser_id = user_b if winner_id == user_a else user_a
    challenge.winner_user_id = winner_id
    return winner_id, loser_id
