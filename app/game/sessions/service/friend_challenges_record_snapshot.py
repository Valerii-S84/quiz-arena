from __future__ import annotations

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.types import FriendChallengeSnapshot


def _build_friend_challenge_snapshot(challenge: FriendChallenge) -> FriendChallengeSnapshot:
    return FriendChallengeSnapshot(
        challenge_id=challenge.id,
        invite_token=challenge.invite_token,
        challenge_type=challenge.challenge_type,
        mode_code=challenge.mode_code,
        access_type=challenge.access_type,
        status=challenge.status,
        creator_user_id=challenge.creator_user_id,
        opponent_user_id=challenge.opponent_user_id,
        question_ids=tuple(challenge.question_ids or []),
        current_round=challenge.current_round,
        total_rounds=challenge.total_rounds,
        creator_finished_at=challenge.creator_finished_at,
        opponent_finished_at=challenge.opponent_finished_at,
        series_id=challenge.series_id,
        series_game_number=challenge.series_game_number,
        series_best_of=challenge.series_best_of,
        creator_score=challenge.creator_score,
        opponent_score=challenge.opponent_score,
        winner_user_id=challenge.winner_user_id,
        expires_at=challenge.expires_at,
        tournament_match_id=challenge.tournament_match_id,
    )
