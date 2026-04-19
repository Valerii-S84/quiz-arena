from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.game.sessions.errors import InvalidAnswerOptionError, SessionNotFoundError
from app.game.sessions.service import sessions_submit_runtime as sessions_submit
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
SESSION_ID = UUID("123e4567-e89b-12d3-a456-426614174000")


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


def _quiz_session(
    *,
    user_id: int = 7,
    status: str = "STARTED",
    source: str = "MENU",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=SESSION_ID,
        user_id=user_id,
        mode_code="QUICK_MIX_A1A2",
        source=source,
        status=status,
        question_id="q-1",
        started_at=NOW_UTC,
        completed_at=None,
        friend_challenge_round=2,
        local_date_berlin=date(2026, 4, 19),
    )


@pytest.mark.asyncio
async def test_submit_answer_rejects_invalid_option() -> None:
    with pytest.raises(InvalidAnswerOptionError):
        await sessions_submit.submit_answer(
            _Session(),
            user_id=7,
            session_id=SESSION_ID,
            selected_option=4,
            idempotency_key="answer:bad-option",
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_submit_answer_returns_replay_for_existing_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_attempt = SimpleNamespace(session_id=SESSION_ID)
    replay_session = _quiz_session()
    expected_result = SimpleNamespace(idempotent_replay=True)

    async def _unexpected_get_by_id_for_update(*_args, **_kwargs):
        pytest.fail("session row should not be locked when idempotent replay already exists")

    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo,
        "get_by_idempotency_key",
        _async_return(existing_attempt),
    )
    monkeypatch.setattr(
        sessions_submit.QuizSessionsRepo,
        "get_by_id",
        _async_return(replay_session),
    )
    monkeypatch.setattr(
        sessions_submit.QuizSessionsRepo,
        "get_by_id_for_update",
        _unexpected_get_by_id_for_update,
    )
    monkeypatch.setattr(
        sessions_submit,
        "build_replay_answer_result",
        _async_return(expected_result),
    )

    result = await sessions_submit.submit_answer(
        _Session(),
        user_id=7,
        session_id=SESSION_ID,
        selected_option=0,
        idempotency_key="answer:replay",
        now_utc=NOW_UTC,
    )

    assert result is expected_result


@pytest.mark.asyncio
@pytest.mark.parametrize("quiz_session", [None, _quiz_session(user_id=8)])
async def test_submit_answer_rejects_missing_or_foreign_session(
    monkeypatch: pytest.MonkeyPatch,
    quiz_session: SimpleNamespace | None,
) -> None:
    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo,
        "get_by_idempotency_key",
        _async_return(None),
    )
    monkeypatch.setattr(
        sessions_submit.QuizSessionsRepo,
        "get_by_id_for_update",
        _async_return(quiz_session),
    )

    with pytest.raises(SessionNotFoundError):
        await sessions_submit.submit_answer(
            _Session(),
            user_id=7,
            session_id=SESSION_ID,
            selected_option=0,
            idempotency_key=f"answer:missing:{uuid4().hex[:6]}",
            now_utc=NOW_UTC,
        )
