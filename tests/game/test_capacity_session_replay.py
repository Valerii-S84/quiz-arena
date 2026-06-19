from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.quiz_sessions import QuizSession
from app.game.sessions.errors import SessionNotFoundError
from app.game.sessions.service import sessions_start, sessions_submit, sessions_submit_replay
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_regular_start_replay_returns_existing_session_without_energy_consume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quiz_session = _started_session()

    async def _unexpected_energy_consume(*_args, **_kwargs):
        pytest.fail("idempotent start replay must not consume energy again")

    async def _get_question_by_id(*_args, **_kwargs):
        return SimpleNamespace(
            question_id=quiz_session.question_id,
            text="Frage?",
            options=("A", "B", "C", "D"),
            category="Grammatik",
        )

    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo,
        "get_by_idempotency_key",
        _async_return(quiz_session),
    )
    monkeypatch.setattr(sessions_start.EnergyService, "consume_quiz", _unexpected_energy_consume)
    monkeypatch.setattr("app.game.sessions.service.get_question_by_id", _get_question_by_id)

    result = await sessions_start.start_session(
        _Session(),
        user_id=11,
        mode_code="MENU_MODE",
        source="MENU",
        idempotency_key="start:menu",
        now_utc=NOW_UTC,
    )

    assert result.idempotent_replay is True
    assert result.session.session_id == quiz_session.id
    assert result.energy_free == 0
    assert result.energy_paid == 0


def _started_session() -> QuizSession:
    return QuizSession(
        id=uuid4(),
        user_id=11,
        mode_code="MENU_MODE",
        source="MENU",
        status="STARTED",
        energy_cost_total=1,
        question_id="q-1",
        started_at=NOW_UTC - timedelta(seconds=3),
        completed_at=None,
        local_date_berlin=NOW_UTC.date(),
        idempotency_key="start:menu",
    )


@pytest.mark.asyncio
async def test_repeated_callback_replays_locked_completed_session_without_second_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quiz_session = _started_session()
    attempts: list[object] = []

    monkeypatch.setattr(
        sessions_submit.QuizSessionsRepo,
        "get_by_id_for_update",
        _async_return(quiz_session),
    )
    monkeypatch.setattr(
        sessions_submit,
        "_load_question_for_session",
        _async_return(
            SimpleNamespace(
                question_id="q-1",
                correct_option=1,
                options=("A", "B", "C", "D"),
                level="A1",
            )
        ),
    )
    monkeypatch.setattr(sessions_submit.QuizAttemptsRepo, "create", _capture_attempt(attempts))
    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo, "get_latest_for_session", _latest_attempt(attempts)
    )
    monkeypatch.setattr(
        sessions_submit,
        "_apply_friend_challenge_answer",
        _async_return((None, False, False)),
    )
    monkeypatch.setattr(
        sessions_submit.StreakService,
        "record_activity",
        _async_return(SimpleNamespace(current_streak=2, best_streak=5)),
    )
    monkeypatch.setattr(
        sessions_submit_replay.StreakService,
        "sync_rollover",
        _async_return(SimpleNamespace(current_streak=2, best_streak=5)),
    )

    first = await sessions_submit.submit_answer(
        _Session(),
        user_id=11,
        session_id=quiz_session.id,
        selected_option=1,
        idempotency_key="answer:first-callback",
        now_utc=NOW_UTC,
    )
    second = await sessions_submit.submit_answer(
        _Session(),
        user_id=11,
        session_id=quiz_session.id,
        selected_option=1,
        idempotency_key="answer:repeated-callback-with-new-id",
        now_utc=NOW_UTC + timedelta(seconds=1),
    )

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert quiz_session.status == "COMPLETED"
    assert quiz_session.completed_at == NOW_UTC
    assert len(attempts) == 1
    assert second.session_id == quiz_session.id
    assert second.question_id == "q-1"


@pytest.mark.asyncio
async def test_completed_foreign_session_still_fails_before_replay_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quiz_session = _started_session()
    quiz_session.status = "COMPLETED"
    quiz_session.user_id = 99

    async def _unexpected_latest_attempt(*_args, **_kwargs):
        pytest.fail("foreign sessions must not reach replay lookup")

    monkeypatch.setattr(
        sessions_submit.QuizSessionsRepo,
        "get_by_id_for_update",
        _async_return(quiz_session),
    )
    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo,
        "get_latest_for_session",
        _unexpected_latest_attempt,
    )

    with pytest.raises(SessionNotFoundError):
        await sessions_submit.submit_answer(
            _Session(),
            user_id=11,
            session_id=quiz_session.id,
            selected_option=1,
            idempotency_key="answer:foreign",
            now_utc=NOW_UTC,
        )


def _capture_attempt(target: list[object]):
    async def _inner(*_args, **kwargs):
        target.append(kwargs["attempt"])
        return kwargs["attempt"]

    return _inner


def _latest_attempt(source: list[object]):
    async def _inner(*_args, **_kwargs):
        return source[-1] if source else None

    return _inner


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
