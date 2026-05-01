from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import ArenaDuelAcceptContext, ArenaDuelsRepo
from tests.game.arena_duels_accept_support import active_duel, challenger_attempt
from tests.type_helpers import AsyncSessionStub, ScalarResult


@pytest.mark.asyncio
async def test_accept_context_lookup_locks_duel_and_existing_attempt() -> None:
    duel = active_duel()
    attempt = challenger_attempt(duel_id=duel.id)
    session = _AcceptContextRecordingSession(duel=duel, attempt=attempt)

    context = await ArenaDuelsRepo.get_accept_context_for_update(
        session,
        duel_id=duel.id,
        user_id=attempt.user_id,
    )

    assert context == ArenaDuelAcceptContext(duel=duel, existing_attempt=attempt)
    assert len(session.statements) == 2
    duel_query = _postgres_sql(session.statements[0])
    attempt_query = _postgres_sql(session.statements[1])
    assert "FROM arena_duels" in duel_query
    assert "FOR UPDATE" in duel_query
    assert "arena_attempts.arena_duel_id" in attempt_query
    assert "arena_attempts.user_id" in attempt_query
    assert "FOR UPDATE" in attempt_query


@pytest.mark.asyncio
async def test_accept_context_lookup_stops_when_duel_is_missing() -> None:
    session = _AcceptContextRecordingSession(duel=None, attempt=None)

    context = await ArenaDuelsRepo.get_accept_context_for_update(
        session,
        duel_id=active_duel().id,
        user_id=22,
    )

    assert context is None
    assert len(session.statements) == 1
    assert "FROM arena_duels" in _postgres_sql(session.statements[0])


@pytest.mark.asyncio
async def test_accept_context_lookup_allows_missing_existing_attempt() -> None:
    duel = active_duel()
    session = _AcceptContextRecordingSession(duel=duel, attempt=None)

    context = await ArenaDuelsRepo.get_accept_context_for_update(
        session,
        duel_id=duel.id,
        user_id=22,
    )

    assert context == ArenaDuelAcceptContext(duel=duel, existing_attempt=None)
    assert len(session.statements) == 2


class _AcceptContextRecordingSession(AsyncSessionStub):
    def __init__(self, *, duel: ArenaDuel | None, attempt: ArenaAttempt | None) -> None:
        self.statements: list[object] = []
        self._duel = duel
        self._attempt = attempt

    async def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return ScalarResult(self._duel)
        return ScalarResult(self._attempt)


def _postgres_sql(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))
