from __future__ import annotations

from app.game.sessions.service import friend_challenges_tournament_progress
from tests.game.friend_challenges_unit_support import NOW_UTC, challenge


def test_tournament_progress_helper_fields_are_selected_per_user() -> None:
    row = challenge(
        creator_score=5,
        opponent_score=3,
        creator_finished_at=NOW_UTC,
        opponent_finished_at=None,
    )

    assert friend_challenges_tournament_progress._score_for_user(challenge=row, user_id=11) == 5
    assert friend_challenges_tournament_progress._score_for_user(challenge=row, user_id=22) == 3
    assert (
        friend_challenges_tournament_progress._finished_at_for_user(challenge=row, user_id=11)
        == NOW_UTC
    )
    assert (
        friend_challenges_tournament_progress._finished_at_for_user(challenge=row, user_id=22)
        is None
    )
