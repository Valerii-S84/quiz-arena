from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, Table

from app.db.models.quiz_sessions import QuizSession
from app.game.sessions.errors import FriendChallengeAccessError
from app.game.sessions.service import sessions_start
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)


def test_arena_session_columns_are_source_scoped_in_model_and_migration() -> None:
    source_link = _constraint_sql("ck_quiz_sessions_arena_source_link")
    round_link = _constraint_sql("ck_quiz_sessions_arena_round_consistency")
    migration = Path("alembic/versions/f7a8b9c0d1e2_m47_open_arena_foundation.py").read_text()

    assert "source = 'ARENA_DUEL'" in source_link
    assert "source != 'ARENA_DUEL'" in source_link
    assert "arena_attempt_id IS NULL" in source_link
    assert "arena_round IS NULL" in source_link
    assert "(arena_round IS NULL) OR (arena_round >= 1 AND arena_round <= 7)" in round_link
    assert "source = 'ARENA_DUEL' AND arena_attempt_id IS NOT NULL" in migration
    assert "source != 'ARENA_DUEL'" in migration
    assert "AND arena_attempt_id IS NULL AND arena_round IS NULL" in migration


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attempt",
    [
        None,
        SimpleNamespace(
            user_id=12,
            role="CHALLENGER",
            score=None,
            time_ms=None,
            result=None,
            completed_at=None,
        ),
        SimpleNamespace(
            user_id=11,
            role="INVALID",
            score=None,
            time_ms=None,
            result=None,
            completed_at=None,
        ),
        SimpleNamespace(
            user_id=11,
            role="CHALLENGER",
            score=0,
            time_ms=None,
            result=None,
            completed_at=None,
        ),
        SimpleNamespace(
            user_id=11,
            role="CHALLENGER",
            score=None,
            time_ms=None,
            result=None,
            completed_at=NOW_UTC,
        ),
    ],
)
async def test_arena_start_rejects_attempts_not_owned_or_not_open(
    monkeypatch: pytest.MonkeyPatch,
    attempt: object | None,
) -> None:
    async def _no_existing_session(*_args, **_kwargs):
        return None

    async def _fake_get_attempt(*_args, **_kwargs):
        return attempt

    async def _unexpected_create(*_args, **_kwargs):
        pytest.fail("invalid ARENA_DUEL attempt must not create a quiz session")

    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo,
        "get_by_idempotency_key",
        _no_existing_session,
    )
    monkeypatch.setattr(
        sessions_start.ArenaAttemptsRepo,
        "get_by_id_for_update",
        _fake_get_attempt,
    )
    monkeypatch.setattr(sessions_start.QuizSessionsRepo, "create", _unexpected_create)

    with pytest.raises(FriendChallengeAccessError):
        await sessions_start.start_session(
            AsyncSessionStub(),
            user_id=11,
            mode_code="QUICK_MIX_A1A2",
            source="ARENA_DUEL",
            idempotency_key="arena:bad-attempt",
            now_utc=NOW_UTC,
            arena_attempt_id=uuid4(),
            arena_round=1,
            forced_question_id="arena-q-1",
            duel_limit_checked=True,
        )


@pytest.mark.asyncio
async def test_arena_start_rejects_out_of_range_round_before_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_existing_session(*_args, **_kwargs):
        return None

    async def _unexpected_get_attempt(*_args, **_kwargs):
        pytest.fail("invalid arena_round must fail before attempt lookup")

    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo,
        "get_by_idempotency_key",
        _no_existing_session,
    )
    monkeypatch.setattr(
        sessions_start.ArenaAttemptsRepo,
        "get_by_id_for_update",
        _unexpected_get_attempt,
    )

    with pytest.raises(FriendChallengeAccessError):
        await sessions_start.start_session(
            AsyncSessionStub(),
            user_id=11,
            mode_code="QUICK_MIX_A1A2",
            source="ARENA_DUEL",
            idempotency_key="arena:bad-round",
            now_utc=NOW_UTC,
            arena_attempt_id=uuid4(),
            arena_round=8,
            duel_limit_checked=True,
        )


def _constraint_sql(name: str) -> str:
    table = cast(Table, QuizSession.__table__)
    constraint = next(constraint for constraint in table.constraints if constraint.name == name)
    assert isinstance(constraint, CheckConstraint)
    return str(constraint.sqltext)
