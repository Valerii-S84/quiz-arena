from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.game.friend_challenges.constants import (
    DUEL_STATUS_ACCEPTED,
    DUEL_STATUS_COMPLETED,
    DUEL_STATUS_PENDING,
)
from app.game.sessions.service.sessions_submit_friend_challenge_state import (
    _FriendChallengeAnswerState,
)
from app.game.sessions.service.sessions_submit_friend_challenge_transitions import (
    apply_playable_friend_challenge_answer,
    is_waiting_for_opponent,
)
from tests.type_helpers import build_friend_challenge

NOW_UTC = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def _state(**challenge_overrides: object) -> _FriendChallengeAnswerState:
    payload: dict[str, object] = {
        "status": DUEL_STATUS_ACCEPTED,
        "creator_user_id": 10,
        "opponent_user_id": 20,
        "total_rounds": 3,
    }
    payload.update(challenge_overrides)
    challenge = build_friend_challenge(**payload)
    return _FriendChallengeAnswerState(
        challenge=challenge,
        answered_round=1,
        has_opponent=challenge.opponent_user_id is not None,
        is_creator=True,
    )


def test_apply_playable_friend_challenge_answer_advances_pending_creator_round() -> None:
    state = _state(
        status=DUEL_STATUS_PENDING,
        opponent_user_id=None,
        total_rounds=5,
    )

    round_completed = apply_playable_friend_challenge_answer(
        state,
        is_correct=True,
        now_utc=NOW_UTC,
    )

    assert round_completed is False
    assert state.challenge.creator_score == 1
    assert state.challenge.creator_answered_round == 1
    assert state.challenge.current_round == 2
    assert state.challenge.status == DUEL_STATUS_PENDING
    assert is_waiting_for_opponent(state) is True


def test_apply_playable_friend_challenge_answer_marks_round_completed_with_opponent() -> None:
    challenge_state = _state(
        creator_answered_round=1,
        creator_score=1,
        current_round=1,
        total_rounds=3,
    )
    challenge_state.is_creator = False

    round_completed = apply_playable_friend_challenge_answer(
        challenge_state,
        is_correct=True,
        now_utc=NOW_UTC,
    )

    assert round_completed is True
    assert challenge_state.challenge.opponent_score == 1
    assert challenge_state.challenge.opponent_answered_round == 1
    assert challenge_state.challenge.current_round == 2
    assert challenge_state.challenge.status == DUEL_STATUS_ACCEPTED
    assert is_waiting_for_opponent(challenge_state) is False


@pytest.mark.parametrize(
    ("opponent_score", "expected_winner_user_id"),
    [(0, 10), (1, None)],
    ids=["creator_wins", "tie"],
)
def test_apply_playable_friend_challenge_answer_completes_duel_on_final_round(
    opponent_score: int,
    expected_winner_user_id: int | None,
) -> None:
    challenge_state = _state(
        creator_answered_round=1,
        creator_score=1,
        current_round=1,
        total_rounds=1,
    )
    challenge_state.is_creator = False
    challenge_state.challenge.opponent_score = opponent_score

    round_completed = apply_playable_friend_challenge_answer(
        challenge_state,
        is_correct=False,
        now_utc=NOW_UTC,
    )

    assert round_completed is True
    assert challenge_state.challenge.status == DUEL_STATUS_COMPLETED
    assert challenge_state.challenge.current_round == 1
    assert challenge_state.challenge.completed_at == NOW_UTC
    assert challenge_state.challenge.creator_finished_at == NOW_UTC
    assert challenge_state.challenge.opponent_finished_at == NOW_UTC
    assert challenge_state.challenge.winner_user_id == expected_winner_user_id
    assert is_waiting_for_opponent(challenge_state) is False


def test_apply_playable_friend_challenge_answer_returns_false_when_not_playable() -> None:
    state = _state(status=DUEL_STATUS_COMPLETED, creator_answered_round=1, creator_score=1)

    round_completed = apply_playable_friend_challenge_answer(
        state,
        is_correct=True,
        now_utc=NOW_UTC,
    )

    assert round_completed is False
    assert state.challenge.creator_score == 1
    assert state.challenge.creator_answered_round == 1
    assert state.challenge.completed_at is None
    assert is_waiting_for_opponent(state) is False
