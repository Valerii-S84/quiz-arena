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


async def _no_existing_session(*_args, **_kwargs):
    return None


def _arena_question_ids() -> list[str]:
    return [f"arena-q-{number}" for number in range(1, 8)]


def _arena_start_context(*, attempt: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        attempt=attempt
        or SimpleNamespace(
            user_id=11,
            role="CHALLENGER",
            score=None,
            time_ms=None,
            result=None,
            completed_at=None,
        ),
        duel=SimpleNamespace(
            mode_code="QUICK_MIX_A1A2",
            question_ids=_arena_question_ids(),
        ),
    )


async def _open_arena_start_context(*_args, **_kwargs):
    return _arena_start_context()


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


def test_arena_migration_downgrade_removes_arena_sessions_before_old_source_check() -> None:
    migration = Path("alembic/versions/f7a8b9c0d1e2_m47_open_arena_foundation.py").read_text()

    delete_arena_attempts = migration.index("DELETE FROM quiz_attempts")
    delete_arena_sessions = migration.index("DELETE FROM quiz_sessions WHERE source = 'ARENA_DUEL'")
    restore_old_source_check = migration.index(
        "source IN ('MENU','DAILY_CHALLENGE','FRIEND_CHALLENGE','TOURNAMENT')"
    )

    assert delete_arena_attempts < delete_arena_sessions
    assert delete_arena_sessions < restore_old_source_check


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
    async def _fake_get_start_context(*_args, **_kwargs):
        if attempt is None:
            return None
        return _arena_start_context(attempt=attempt)

    async def _unexpected_create(*_args, **_kwargs):
        pytest.fail("invalid ARENA_DUEL attempt must not create a quiz session")

    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo,
        "get_by_idempotency_key",
        _no_existing_session,
    )
    monkeypatch.setattr(
        sessions_start.ArenaAttemptsRepo,
        "get_start_context_for_update",
        _fake_get_start_context,
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
@pytest.mark.parametrize(
    ("mode_code", "forced_question_id"),
    [
        ("ARTIKEL_SPRINT", "arena-q-1"),
        ("QUICK_MIX_A1A2", "arena-q-2"),
    ],
)
async def test_arena_start_rejects_duel_mode_or_question_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    mode_code: str,
    forced_question_id: str,
) -> None:
    async def _unexpected_create(*_args, **_kwargs):
        pytest.fail("ARENA_DUEL metadata mismatch must not create a quiz session")

    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo,
        "get_by_idempotency_key",
        _no_existing_session,
    )
    monkeypatch.setattr(
        sessions_start.ArenaAttemptsRepo,
        "get_start_context_for_update",
        _open_arena_start_context,
    )
    monkeypatch.setattr(sessions_start.QuizSessionsRepo, "create", _unexpected_create)

    with pytest.raises(FriendChallengeAccessError):
        await sessions_start.start_session(
            AsyncSessionStub(),
            user_id=11,
            mode_code=mode_code,
            source="ARENA_DUEL",
            idempotency_key="arena:metadata-mismatch",
            now_utc=NOW_UTC,
            arena_attempt_id=uuid4(),
            arena_round=1,
            forced_question_id=forced_question_id,
            duel_limit_checked=True,
        )


@pytest.mark.asyncio
async def test_arena_start_rejects_missing_planned_question_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _missing_question(*_args, **_kwargs):
        return None

    async def _unexpected_select_question(*_args, **_kwargs):
        pytest.fail("ARENA_DUEL must not fall back to random question selection")

    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo,
        "get_by_idempotency_key",
        _no_existing_session,
    )
    monkeypatch.setattr(
        sessions_start.ArenaAttemptsRepo,
        "get_start_context_for_update",
        _open_arena_start_context,
    )

    from app.game.sessions import service as service_module

    monkeypatch.setattr(service_module, "get_question_by_id", _missing_question)
    monkeypatch.setattr(service_module, "select_question_for_mode", _unexpected_select_question)

    with pytest.raises(FriendChallengeAccessError):
        await sessions_start.start_session(
            AsyncSessionStub(),
            user_id=11,
            mode_code="QUICK_MIX_A1A2",
            source="ARENA_DUEL",
            idempotency_key="arena:missing-planned-question",
            now_utc=NOW_UTC,
            arena_attempt_id=uuid4(),
            arena_round=1,
            duel_limit_checked=True,
        )


@pytest.mark.asyncio
async def test_arena_start_rejects_out_of_range_round_before_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_get_start_context(*_args, **_kwargs):
        pytest.fail("invalid arena_round must fail before attempt lookup")

    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo,
        "get_by_idempotency_key",
        _no_existing_session,
    )
    monkeypatch.setattr(
        sessions_start.ArenaAttemptsRepo,
        "get_start_context_for_update",
        _unexpected_get_start_context,
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
