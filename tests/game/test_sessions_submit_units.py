from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.quiz_sessions import QuizSession
from app.game.sessions.errors import InvalidAnswerOptionError, SessionNotFoundError
from app.game.sessions.service import sessions_submit
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _quiz_session(
    *, source: str, mode_code: str = "QUICK_MIX_A1A2", status: str = "STARTED"
) -> QuizSession:
    return QuizSession(
        id=uuid4(),
        user_id=11,
        mode_code=mode_code,
        source=source,
        status=status,
        energy_cost_total=0,
        question_id="q-1",
        daily_run_id=uuid4() if source == "DAILY_CHALLENGE" else None,
        friend_challenge_id=None,
        friend_challenge_round=None,
        arena_attempt_id=None,
        arena_round=None,
        started_at=NOW_UTC - timedelta(seconds=5),
        local_date_berlin=NOW_UTC.date(),
        idempotency_key=f"session:{uuid4()}",
    )


@pytest.mark.asyncio
async def test_submit_answer_rejects_invalid_option_before_io() -> None:
    with pytest.raises(InvalidAnswerOptionError):
        await sessions_submit.submit_answer(
            _Session(),
            user_id=11,
            session_id=uuid4(),
            selected_option=4,
            idempotency_key="bad-option",
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("quiz_session", [None, _quiz_session(source="MENU")])
async def test_submit_answer_rejects_missing_or_foreign_session(
    monkeypatch: pytest.MonkeyPatch,
    quiz_session,
) -> None:
    if quiz_session is not None:
        quiz_session.user_id = 99

    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo, "get_by_idempotency_key", _async_return(None)
    )
    monkeypatch.setattr(
        sessions_submit.QuizSessionsRepo, "get_by_id_for_update", _async_return(quiz_session)
    )

    with pytest.raises(SessionNotFoundError):
        await sessions_submit.submit_answer(
            _Session(),
            user_id=11,
            session_id=uuid4(),
            selected_option=1,
            idempotency_key="missing-session",
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_submit_answer_completes_daily_session_and_returns_daily_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_attempts: list[object] = []
    quiz_session = _quiz_session(source="DAILY_CHALLENGE", mode_code="DAILY_CHALLENGE")
    question = SimpleNamespace(
        question_id="daily-q",
        correct_option=2,
        options=("A", "B", "C", "D"),
        level="A1",
    )
    daily_state = SimpleNamespace(
        current_streak=4,
        best_streak=6,
        daily_run_id=quiz_session.daily_run_id,
        current_question=3,
        total_questions=7,
        score=2,
        completed=False,
    )

    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo, "get_by_idempotency_key", _async_return(None)
    )
    monkeypatch.setattr(
        sessions_submit.QuizSessionsRepo, "get_by_id_for_update", _async_return(quiz_session)
    )
    monkeypatch.setattr(sessions_submit, "_load_question_for_session", _async_return(question))
    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo,
        "create",
        _capture_attempt(created_attempts),
    )
    monkeypatch.setattr(sessions_submit, "apply_daily_answer", _async_return(daily_state))

    result = await sessions_submit.submit_answer(
        _Session(),
        user_id=11,
        session_id=quiz_session.id,
        selected_option=2,
        idempotency_key="daily:fresh",
        now_utc=NOW_UTC,
    )

    assert quiz_session.status == "COMPLETED"
    assert quiz_session.completed_at == NOW_UTC
    assert created_attempts
    assert result.daily_run_id == daily_state.daily_run_id
    assert result.daily_current_question == 3
    assert result.daily_score == 2
    assert result.selected_answer_text == "C"
    assert result.correct_answer_text == "C"
    assert result.next_preferred_level is None


@pytest.mark.asyncio
async def test_submit_answer_records_non_daily_activity_and_advances_adaptive_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_attempts: list[object] = []
    quiz_session = _quiz_session(source="MENU")
    question = SimpleNamespace(
        question_id="menu-q",
        correct_option=1,
        options=("A", "B", "C", "D"),
        level="A2",
    )

    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo, "get_by_idempotency_key", _async_return(None)
    )
    monkeypatch.setattr(
        sessions_submit.QuizSessionsRepo, "get_by_id_for_update", _async_return(quiz_session)
    )
    monkeypatch.setattr(sessions_submit, "_load_question_for_session", _async_return(question))
    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo,
        "create",
        _capture_attempt(created_attempts),
    )
    monkeypatch.setattr(
        sessions_submit,
        "_apply_friend_challenge_answer",
        _async_return((None, False, False)),
    )
    monkeypatch.setattr(
        sessions_submit.StreakService,
        "record_activity",
        _async_return(SimpleNamespace(current_streak=7, best_streak=9)),
    )
    monkeypatch.setattr(
        sessions_submit,
        "check_and_advance",
        _async_return(("B1", 0, 0)),
    )

    result = await sessions_submit.submit_answer(
        _Session(),
        user_id=11,
        session_id=quiz_session.id,
        selected_option=1,
        idempotency_key="menu:fresh",
        now_utc=NOW_UTC,
    )

    assert created_attempts
    assert result.current_streak == 7
    assert result.best_streak == 9
    assert result.next_preferred_level == "B1"
    assert result.next_preferred_mix_step == 0
    assert result.selected_answer_text == "B"
    assert result.correct_answer_text == "B"


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _capture_attempt(target: list[object]):
    async def _inner(*_args, **kwargs):
        target.append(kwargs["attempt"])

    return _inner
