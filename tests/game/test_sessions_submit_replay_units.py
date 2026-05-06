from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.db.models.quiz_sessions import QuizSession
from app.game.sessions.service import sessions_submit_replay
from tests.game.friend_challenges_unit_support import challenge
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


def _quiz_session(*, source: str) -> QuizSession:
    return QuizSession(
        id=uuid4(),
        user_id=11,
        mode_code="QUICK_MIX_A1A2" if source != "DAILY_CHALLENGE" else "DAILY_CHALLENGE",
        source=source,
        status="COMPLETED",
        energy_cost_total=0,
        question_id="q-1",
        daily_run_id=uuid4() if source == "DAILY_CHALLENGE" else None,
        friend_challenge_id=uuid4() if source == "FRIEND_CHALLENGE" else None,
        friend_challenge_round=2 if source == "FRIEND_CHALLENGE" else None,
        arena_attempt_id=uuid4() if source == "ARENA_DUEL" else None,
        arena_round=3 if source == "ARENA_DUEL" else None,
        started_at=NOW_UTC - timedelta(seconds=5),
        local_date_berlin=NOW_UTC.date(),
        idempotency_key=f"session:{uuid4()}",
    )


@pytest.mark.asyncio
async def test_build_replay_answer_result_defaults_without_session_or_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sessions_submit_replay.StreakService,
        "sync_rollover",
        _async_return(SimpleNamespace(current_streak=2, best_streak=5)),
    )

    result = await sessions_submit_replay.build_replay_answer_result(
        AsyncSessionStub(),
        user_id=11,
        replay_session=None,
        replay_attempt=None,
        now_utc=NOW_UTC,
    )

    assert result.session_id == UUID(int=0)
    assert result.question_id == ""
    assert result.is_correct is False
    assert result.current_streak == 2
    assert result.friend_challenge is None
    assert result.daily_run_id is None


@pytest.mark.asyncio
async def test_build_replay_answer_result_attaches_friend_snapshot_and_waiting_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_session = _quiz_session(source="FRIEND_CHALLENGE")
    replay_attempt: Any = SimpleNamespace(
        session_id=replay_session.id, question_id="q-1", is_correct=True
    )
    duel = challenge(id=replay_session.friend_challenge_id, creator_user_id=11, opponent_user_id=22)

    monkeypatch.setattr(
        sessions_submit_replay.StreakService,
        "sync_rollover",
        _async_return(SimpleNamespace(current_streak=3, best_streak=6)),
    )
    monkeypatch.setattr(
        sessions_submit_replay.FriendChallengesRepo,
        "get_by_id",
        _async_return(duel),
    )

    result = await sessions_submit_replay.build_replay_answer_result(
        AsyncSessionStub(),
        user_id=11,
        replay_session=replay_session,
        replay_attempt=replay_attempt,
        now_utc=NOW_UTC,
    )

    assert result.friend_challenge is not None
    assert result.friend_challenge.challenge_id == duel.id
    assert result.friend_challenge_waiting_for_opponent is True
    assert result.friend_challenge_answered_round == 2
    assert result.question_id == "q-1"
    assert result.is_correct is True


@pytest.mark.asyncio
async def test_build_replay_answer_result_uses_daily_replay_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_session = _quiz_session(source="DAILY_CHALLENGE")
    daily_state = SimpleNamespace(
        daily_run_id=replay_session.daily_run_id,
        current_question=7,
        total_questions=7,
        score=6,
        completed=True,
        current_streak=4,
        best_streak=8,
    )

    monkeypatch.setattr(
        sessions_submit_replay.StreakService,
        "sync_rollover",
        _async_return(SimpleNamespace(current_streak=1, best_streak=2)),
    )
    monkeypatch.setattr(
        sessions_submit_replay,
        "build_daily_replay_state",
        _async_return(daily_state),
    )

    result = await sessions_submit_replay.build_replay_answer_result(
        AsyncSessionStub(),
        user_id=11,
        replay_session=replay_session,
        replay_attempt=None,
        now_utc=NOW_UTC,
    )

    assert result.daily_run_id == replay_session.daily_run_id
    assert result.daily_current_question == 7
    assert result.daily_score == 6
    assert result.daily_completed is True
    assert result.current_streak == 4
    assert result.best_streak == 8


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
