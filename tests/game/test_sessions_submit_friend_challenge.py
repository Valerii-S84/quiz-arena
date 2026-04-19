from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.db.models.quiz_sessions import QuizSession
from app.game.sessions.service import sessions_submit_friend_challenge
from app.game.sessions.service.sessions_submit_friend_challenge_state import (
    _FriendChallengeAnswerState,
)
from app.game.sessions.types import FriendChallengeSnapshot
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
TOURNAMENT_MATCH_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


def _quiz_session(
    *,
    user_id: int = 10,
    friend_challenge_id=None,
    friend_challenge_round: int | None = 2,
) -> QuizSession:
    return QuizSession(
        id=uuid4(),
        user_id=user_id,
        mode_code="QUICK_MIX_A1A2",
        source="FRIEND_CHALLENGE",
        status="STARTED",
        energy_cost_total=0,
        question_id="q-1",
        daily_run_id=None,
        friend_challenge_id=friend_challenge_id,
        friend_challenge_round=friend_challenge_round,
        started_at=NOW_UTC,
        completed_at=None,
        local_date_berlin=date(2026, 3, 15),
        idempotency_key=f"quiz:{uuid4().hex}",
    )


def _snapshot(challenge_id) -> FriendChallengeSnapshot:
    return FriendChallengeSnapshot(
        challenge_id=challenge_id,
        invite_token="invite-token",
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        status="ACCEPTED",
        creator_user_id=10,
        opponent_user_id=20,
        current_round=2,
        total_rounds=7,
        creator_score=1,
        opponent_score=0,
    )


@pytest.mark.asyncio
async def test_apply_friend_challenge_answer_returns_empty_tuple_when_state_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quiz_session = _quiz_session(friend_challenge_id=uuid4())

    async def _unexpected_apply(*args, **kwargs):
        del args, kwargs
        pytest.fail(
            "playable answer application should not run when no friend challenge state exists"
        )

    monkeypatch.setattr(
        sessions_submit_friend_challenge,
        "load_friend_challenge_answer_state",
        _async_return(None),
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge,
        "apply_playable_friend_challenge_answer",
        _unexpected_apply,
    )

    result = await sessions_submit_friend_challenge._apply_friend_challenge_answer(
        _Session(),
        quiz_session=quiz_session,
        user_id=10,
        is_correct=True,
        now_utc=NOW_UTC,
    )

    assert result == (None, False, False)


@pytest.mark.asyncio
async def test_apply_friend_challenge_answer_updates_state_and_emits_followups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(
        creator_user_id=10,
        opponent_user_id=20,
        tournament_match_id=TOURNAMENT_MATCH_ID,
    )
    quiz_session = _quiz_session(friend_challenge_id=challenge.id, friend_challenge_round=2)
    answer_state = _FriendChallengeAnswerState(
        challenge=challenge,
        answered_round=2,
        has_opponent=True,
        is_creator=True,
    )
    snapshot = _snapshot(challenge.id)
    tournament_calls: list[dict[str, object]] = []
    completed_event_calls: list[dict[str, object]] = []

    async def _fake_handle_tournament_duel_progress(*_args, **kwargs) -> None:
        tournament_calls.append(kwargs)

    async def _fake_emit_completed_duel_event_if_needed(*_args, **kwargs) -> None:
        completed_event_calls.append(kwargs)

    monkeypatch.setattr(
        sessions_submit_friend_challenge,
        "load_friend_challenge_answer_state",
        _async_return(answer_state),
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge,
        "apply_playable_friend_challenge_answer",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge,
        "handle_tournament_duel_progress",
        _fake_handle_tournament_duel_progress,
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: snapshot if challenge_row is challenge else None,
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge,
        "is_waiting_for_opponent",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge,
        "_emit_completed_duel_event_if_needed",
        _fake_emit_completed_duel_event_if_needed,
    )

    result = await sessions_submit_friend_challenge._apply_friend_challenge_answer(
        _Session(),
        quiz_session=quiz_session,
        user_id=10,
        is_correct=True,
        now_utc=NOW_UTC,
    )

    assert result == (snapshot, True, False)
    assert challenge.updated_at == NOW_UTC
    assert tournament_calls == [
        {
            "challenge": challenge,
            "user_id": 10,
            "now_utc": NOW_UTC,
        }
    ]
    assert completed_event_calls == [
        {
            "challenge": challenge,
            "user_id": 10,
            "now_utc": NOW_UTC,
        }
    ]
