from __future__ import annotations

from datetime import datetime

from app.db.models.friend_challenges import FriendChallenge


def is_self_bot_tournament_challenge(*, challenge: FriendChallenge) -> bool:
    return (
        challenge.tournament_match_id is not None
        and challenge.opponent_user_id is not None
        and int(challenge.opponent_user_id) == int(challenge.creator_user_id)
    )


def maybe_complete_self_bot_match(
    *,
    challenge: FriendChallenge,
    now_utc: datetime,
    fixed_bot_score: int | None = None,
) -> None:
    if challenge.status != "CREATOR_DONE" or not is_self_bot_tournament_challenge(
        challenge=challenge
    ):
        return
    if fixed_bot_score is None:
        bot_target = max(
            0,
            min(int(round(int(challenge.total_rounds) * 0.7)), int(challenge.total_rounds) - 1),
        )
        challenge.opponent_score = min(bot_target, max(0, int(challenge.creator_score) - 1))
        challenge.winner_user_id = int(challenge.creator_user_id)
    else:
        challenge.opponent_score = min(max(0, int(fixed_bot_score)), int(challenge.total_rounds))
        challenge.winner_user_id = (
            int(challenge.creator_user_id)
            if int(challenge.creator_score) > int(challenge.opponent_score)
            else None
        )
    challenge.opponent_answered_round = int(challenge.total_rounds)
    challenge.opponent_finished_at = now_utc
    challenge.current_round = int(challenge.total_rounds)
    challenge.status = "COMPLETED"
    challenge.completed_at = now_utc
