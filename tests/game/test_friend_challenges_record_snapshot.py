from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.game.sessions.service import friend_challenges_record_snapshot
from tests.type_helpers import build_friend_challenge

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
EXPLICIT_CHALLENGE_ID = UUID("33333333-3333-3333-3333-333333333333")


def test_build_friend_challenge_snapshot_maps_model_fields() -> None:
    challenge = build_friend_challenge(
        id=EXPLICIT_CHALLENGE_ID,
        invite_token="invite-token",
        creator_user_id=101,
        opponent_user_id=202,
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        question_ids=["q-1", "q-2"],
        current_round=2,
        total_rounds=7,
        series_game_number=3,
        series_best_of=5,
        creator_score=4,
        opponent_score=3,
        winner_user_id=101,
        expires_at=NOW_UTC + timedelta(minutes=10),
    )

    snapshot = friend_challenges_record_snapshot._build_friend_challenge_snapshot(challenge)

    assert snapshot.challenge_id == EXPLICIT_CHALLENGE_ID
    assert snapshot.invite_token == "invite-token"
    assert snapshot.creator_user_id == 101
    assert snapshot.opponent_user_id == 202
    assert snapshot.question_ids == ("q-1", "q-2")
    assert snapshot.current_round == 2
    assert snapshot.total_rounds == 7
    assert snapshot.series_game_number == 3
    assert snapshot.series_best_of == 5
    assert snapshot.creator_score == 4
    assert snapshot.opponent_score == 3
    assert snapshot.winner_user_id == 101
