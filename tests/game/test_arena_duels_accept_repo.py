from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import ArenaDuelAcceptContext, ArenaDuelsRepo
from tests.game.arena_duels_accept_support import active_duel, challenger_attempt
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_accept_context_lookup_locks_duel_and_existing_attempt() -> None:
    duel = active_duel()
    attempt = challenger_attempt(duel_id=duel.id)
    session = _AcceptContextRecordingSession(_RowResult((attempt, duel)))

    context = await ArenaDuelsRepo.get_accept_context_for_update(
        session,
        duel_id=duel.id,
        user_id=attempt.user_id,
    )

    assert context == ArenaDuelAcceptContext(duel=duel, existing_attempt=attempt)
    assert len(session.statements) == 1
    query = _postgres_sql(session.statements[0])
    assert "FROM arena_attempts JOIN arena_duels" in query
    assert "arena_attempts.arena_duel_id" in query
    assert "arena_attempts.user_id" in query
    assert "FOR UPDATE OF arena_attempts, arena_duels" in query


@pytest.mark.asyncio
async def test_accept_context_lookup_stops_when_duel_is_missing() -> None:
    session = _AcceptContextRecordingSession(_RowResult(None), _ScalarResult(None))

    context = await ArenaDuelsRepo.get_accept_context_for_update(
        session,
        duel_id=active_duel().id,
        user_id=22,
    )

    assert context is None
    assert len(session.statements) == 2
    assert "FROM arena_attempts JOIN arena_duels" in _postgres_sql(session.statements[0])
    assert "FROM arena_duels" in _postgres_sql(session.statements[1])
    assert "FOR UPDATE" in _postgres_sql(session.statements[1])


@pytest.mark.asyncio
async def test_accept_context_lookup_allows_missing_existing_attempt() -> None:
    duel = active_duel()
    session = _AcceptContextRecordingSession(
        _RowResult(None),
        _ScalarResult(duel),
        _ScalarResult(None),
    )

    context = await ArenaDuelsRepo.get_accept_context_for_update(
        session,
        duel_id=duel.id,
        user_id=22,
    )

    assert context == ArenaDuelAcceptContext(duel=duel, existing_attempt=None)
    assert len(session.statements) == 3
    recheck_query = _postgres_sql(session.statements[2])
    assert "FROM arena_attempts" in recheck_query
    assert "FOR UPDATE" not in recheck_query


@pytest.mark.asyncio
async def test_accept_context_rechecks_attempt_after_locking_duel() -> None:
    duel = active_duel()
    attempt = challenger_attempt(duel_id=duel.id)
    session = _AcceptContextRecordingSession(
        _RowResult(None),
        _ScalarResult(duel),
        _ScalarResult(attempt),
    )

    context = await ArenaDuelsRepo.get_accept_context_for_update(
        session,
        duel_id=duel.id,
        user_id=attempt.user_id,
    )

    assert context == ArenaDuelAcceptContext(duel=duel, existing_attempt=attempt)
    recheck_query = _postgres_sql(session.statements[2])
    assert "FROM arena_attempts" in recheck_query
    assert "FOR UPDATE" not in recheck_query


@pytest.mark.asyncio
async def test_count_creator_duels_by_access_type_is_server_side() -> None:
    session = _AcceptContextRecordingSession(_CountResult(1))

    count = await ArenaDuelsRepo.count_creator_duels_by_access_type(
        session,
        creator_user_id=11,
        access_type="FREE",
        since=NOW_UTC,
    )

    assert count == 1
    query = _postgres_sql(session.statements[0])
    assert "count(arena_duels.id)" in query
    assert "arena_duels.creator_user_id" in query
    assert "arena_duels.access_type" in query
    assert "arena_duels.source_friend_challenge_id IS NULL" in query
    assert "arena_duels.created_at >=" in query


@pytest.mark.asyncio
async def test_count_challenger_attempts_by_access_type_is_server_side() -> None:
    session = _AcceptContextRecordingSession(_CountResult(3))

    count = await ArenaDuelsRepo.count_challenger_attempts_by_access_type(
        session,
        user_id=22,
        access_type="FREE",
        since=NOW_UTC,
    )

    assert count == 3
    query = _postgres_sql(session.statements[0])
    assert "count(arena_attempts.id)" in query
    assert "arena_attempts.user_id" in query
    assert "arena_attempts.role" in query
    assert "arena_attempts.access_type" in query
    assert "arena_attempts.created_at >=" in query


@pytest.mark.asyncio
async def test_count_paid_ticket_usage_counts_arena_create_and_accept_usage() -> None:
    session = _AcceptContextRecordingSession(_CountResult(1), _CountResult(2))

    count = await ArenaDuelsRepo.count_paid_ticket_usage(session, user_id=22)

    assert count == 3
    duel_query = _postgres_sql(session.statements[0])
    attempt_query = _postgres_sql(session.statements[1])
    assert "FROM arena_duels" in duel_query
    assert "arena_duels.access_type = %(access_type_1)s" in duel_query
    assert "FROM arena_attempts" in attempt_query
    assert "arena_attempts.role = %(role_1)s" in attempt_query
    assert "arena_attempts.access_type = %(access_type_1)s" in attempt_query


class _AcceptContextRecordingSession(AsyncSessionStub):
    def __init__(self, *results: object) -> None:
        self.statements: list[object] = []
        self._results = list(results)

    async def execute(self, statement):
        self.statements.append(statement)
        if not self._results:
            raise AssertionError("unexpected execute() call")
        return self._results.pop(0)


class _RowResult:
    def __init__(self, row: tuple[ArenaAttempt, ArenaDuel] | None) -> None:
        self._row = row

    def one_or_none(self) -> SimpleNamespace | None:
        if self._row is None:
            return None
        return SimpleNamespace(t=self._row)


class _ScalarResult:
    def __init__(self, value: ArenaAttempt | ArenaDuel | None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> ArenaAttempt | ArenaDuel | None:
        return self._value


class _CountResult:
    def __init__(self, value: int) -> None:
        self._value = value

    def scalar_one(self) -> int:
        return self._value


def _postgres_sql(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))
