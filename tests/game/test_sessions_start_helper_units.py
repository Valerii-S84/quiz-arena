from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.sessions.errors import FriendChallengeAccessError, SessionNotFoundError
from app.game.sessions.service import sessions_start
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_start_session_delegates_daily_source_to_start_daily_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = object()
    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo, "get_by_idempotency_key", _async_return(None)
    )
    monkeypatch.setattr(sessions_start, "start_daily_session", _async_return(expected))

    result = await sessions_start.start_session(
        AsyncSessionStub(),
        user_id=11,
        mode_code="DAILY_CHALLENGE",
        source="DAILY_CHALLENGE",
        idempotency_key="daily:start-via-start-session",
        now_utc=NOW_UTC,
    )

    assert result is expected


@pytest.mark.asyncio
async def test_get_session_user_id_returns_owner_and_rejects_missing_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo,
        "get_by_id",
        _async_return(SimpleNamespace(user_id=11)),
    )
    assert await sessions_start.get_session_user_id(AsyncSessionStub(), uuid4()) == 11

    monkeypatch.setattr(sessions_start.QuizSessionsRepo, "get_by_id", _async_return(None))
    with pytest.raises(SessionNotFoundError):
        await sessions_start.get_session_user_id(AsyncSessionStub(), uuid4())


def test_start_helpers_cover_friend_defaults_and_invalid_arena_question_shapes() -> None:
    assert (
        sessions_start._session_question_number(
            source="FRIEND_CHALLENGE", friend_challenge_round=None, arena_round=None
        )
        == 1
    )
    assert (
        sessions_start._session_total_questions(
            source="FRIEND_CHALLENGE", friend_challenge_total_rounds=None
        )
        == 1
    )
    assert sessions_start._arena_duel_question_id("not-a-list", 1) is None
    assert sessions_start._arena_duel_question_id([], 1) is None
    assert sessions_start._arena_duel_question_id([""], 1) is None


def test_arena_attempt_started_before_expiry_and_valid_allow_paths() -> None:
    expires_at = NOW_UTC
    attempt = SimpleNamespace(created_at=NOW_UTC - timedelta(seconds=1))
    assert (
        sessions_start._arena_attempt_started_before_expiry(attempt=attempt, expires_at=expires_at)
        is True
    )

    sessions_start._ensure_arena_duel_allows_attempt_start(
        duel=SimpleNamespace(status="DRAFT", expires_at=NOW_UTC + timedelta(minutes=5)),
        attempt=SimpleNamespace(created_at=None),
        attempt_role="CREATOR_BASELINE",
        now_utc=NOW_UTC,
    )
    sessions_start._ensure_arena_duel_allows_attempt_start(
        duel=SimpleNamespace(status="EXPIRED", expires_at=NOW_UTC),
        attempt=SimpleNamespace(created_at=NOW_UTC - timedelta(seconds=1)),
        attempt_role="CREATOR_BASELINE",
        now_utc=NOW_UTC,
    )
    sessions_start._ensure_arena_duel_allows_attempt_start(
        duel=SimpleNamespace(status="ACTIVE", expires_at=NOW_UTC + timedelta(minutes=5)),
        attempt=SimpleNamespace(created_at=None),
        attempt_role="CHALLENGER",
        now_utc=NOW_UTC,
    )


def test_arena_allow_start_rejects_missing_expiry_type() -> None:
    with pytest.raises(FriendChallengeAccessError):
        sessions_start._ensure_arena_duel_allows_attempt_start(
            duel=SimpleNamespace(status="ACTIVE", expires_at=None),
            attempt=SimpleNamespace(created_at=None),
            attempt_role="CHALLENGER",
            now_utc=NOW_UTC,
        )


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
