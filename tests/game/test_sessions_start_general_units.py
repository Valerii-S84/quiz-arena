from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.sessions.errors import EnergyInsufficientError, FriendChallengeAccessError
from app.game.sessions.service import sessions_start
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_start_session_requires_friend_challenge_metadata_before_energy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_energy(*_args, **_kwargs):
        pytest.fail("friend challenge metadata must be validated before energy")

    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo, "get_by_idempotency_key", _async_return(None)
    )
    monkeypatch.setattr(sessions_start.EnergyService, "consume_quiz", _unexpected_energy)

    with pytest.raises(FriendChallengeAccessError):
        await sessions_start.start_session(
            AsyncSessionStub(),
            user_id=11,
            mode_code="QUICK_MIX_A1A2",
            source="FRIEND_CHALLENGE",
            idempotency_key="friend:start",
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_start_session_raises_when_energy_is_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo, "get_by_idempotency_key", _async_return(None)
    )
    monkeypatch.setattr(
        sessions_start.EnergyService,
        "consume_quiz",
        _async_return(SimpleNamespace(allowed=False, free_energy=0, paid_energy=0)),
    )

    with pytest.raises(EnergyInsufficientError):
        await sessions_start.start_session(
            AsyncSessionStub(),
            user_id=11,
            mode_code="MENU_MODE",
            source="MENU",
            idempotency_key="menu:no-energy",
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_start_session_uses_progression_and_random_selection_for_adaptive_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_sessions = []
    selection_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo, "get_by_idempotency_key", _async_return(None)
    )
    monkeypatch.setattr(
        sessions_start.EnergyService,
        "consume_quiz",
        _async_return(SimpleNamespace(allowed=True, free_energy=1, paid_energy=0)),
    )
    monkeypatch.setattr(
        sessions_start,
        "resolve_start_progression_state",
        _async_return(("A2", 2, ("A2", "B1"))),
    )
    monkeypatch.setattr(
        sessions_start.QuizAttemptsRepo,
        "get_recent_question_ids_for_mode",
        _async_return(["old-q-1", "old-q-2"]),
    )
    monkeypatch.setattr(sessions_start, "select_level_weighted", lambda *_args, **_kwargs: "B1")

    async def _fake_select_question_for_mode(_session, mode_code, **kwargs):
        selection_calls.append({"mode_code": mode_code, **kwargs})
        return SimpleNamespace(
            question_id="selected-q",
            text="Question?",
            options=("a", "b", "c", "d"),
            category="General",
        )

    async def _fake_create(_session, *, quiz_session):
        created_sessions.append(quiz_session)
        quiz_session.id = uuid4()
        return quiz_session

    monkeypatch.setattr(
        "app.game.sessions.service.select_question_for_mode", _fake_select_question_for_mode
    )
    monkeypatch.setattr(sessions_start.QuizSessionsRepo, "create", _fake_create)

    result = await sessions_start.start_session(
        AsyncSessionStub(),
        user_id=11,
        mode_code="QUICK_MIX_A1A2",
        source="MENU",
        idempotency_key="menu:adaptive",
        now_utc=NOW_UTC,
    )

    assert result.energy_free == 1
    assert result.session.question_id == "selected-q"
    assert selection_calls[0]["preferred_level"] == "B1"
    assert selection_calls[0]["allowed_levels"] == ("A2", "B1")
    assert selection_calls[0]["recent_question_ids"] == ["old-q-1", "old-q-2"]
    assert created_sessions[0].question_id == "selected-q"


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
