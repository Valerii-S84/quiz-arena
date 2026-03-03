from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from app.workers.tasks.daily_cup_nonfinishers_summary import (
    _collect_nonfinishers,
    _user_did_not_finish_challenge,
)


def test_user_did_not_finish_challenge_flags_incomplete_creator() -> None:
    challenge = SimpleNamespace(
        id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        creator_user_id=101,
        opponent_user_id=202,
        total_rounds=5,
        creator_finished_at=None,
        opponent_finished_at=datetime.now(timezone.utc),
        creator_answered_round=2,
        opponent_answered_round=5,
    )
    assert _user_did_not_finish_challenge(challenge=challenge, user_id=101) is True
    assert _user_did_not_finish_challenge(challenge=challenge, user_id=202) is False


def test_collect_nonfinishers_skips_bye_and_keeps_only_incomplete_users() -> None:
    challenge_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    matches = [
        SimpleNamespace(
            user_a=101,
            user_b=202,
            friend_challenge_id=challenge_id,
        ),
        SimpleNamespace(
            user_a=303,
            user_b=None,
            friend_challenge_id=None,
        ),
    ]
    challenges_by_id = {
        challenge_id: SimpleNamespace(
            id=challenge_id,
            creator_user_id=101,
            opponent_user_id=202,
            total_rounds=5,
            creator_finished_at=None,
            opponent_finished_at=datetime.now(timezone.utc),
            creator_answered_round=3,
            opponent_answered_round=5,
        )
    }
    nonfinishers = _collect_nonfinishers(matches=matches, challenges_by_id=challenges_by_id)
    assert nonfinishers == {101}
