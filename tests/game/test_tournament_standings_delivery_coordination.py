from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.game.tournaments import standings_delivery_coordination as coordination


class _ScalarResult:
    def scalar_one(self) -> bool:
        return True


class _AdvisoryConnection:
    def __init__(self, shared_lock: asyncio.Lock, *, cancel_on_acquire: bool = False) -> None:
        self.info: dict[str, str] = {}
        self.shared_lock = shared_lock
        self.cancel_on_acquire = cancel_on_acquire
        self.closed = False
        self.invalidated = False
        self.owns_lock = False
        self.parameters: list[tuple[str, str]] = []

    async def execution_options(self, **_kwargs):
        return self

    async def execute(self, statement, params):
        sql = str(statement)
        self.parameters.append((sql, params["lock_key"]))
        if "pg_advisory_unlock" in sql:
            assert self.owns_lock
            self.shared_lock.release()
            self.owns_lock = False
        elif "pg_advisory_lock" in sql:
            await self.shared_lock.acquire()
            self.owns_lock = True
            if self.cancel_on_acquire:
                self.cancel_on_acquire = False
                raise asyncio.CancelledError
        return _ScalarResult()

    async def invalidate(self) -> None:
        self.invalidated = True
        if self.owns_lock:
            self.shared_lock.release()
            self.owns_lock = False

    async def close(self) -> None:
        self.closed = True


class _AdvisoryEngine:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.connections: list[_AdvisoryConnection] = []
        self.cancel_next_acquire = False

    async def connect(self) -> _AdvisoryConnection:
        connection = _AdvisoryConnection(
            self.lock,
            cancel_on_acquire=self.cancel_next_acquire,
        )
        self.cancel_next_acquire = False
        self.connections.append(connection)
        return connection


@pytest.mark.asyncio
async def test_exception_releases_mutex_and_retry_acquires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _AdvisoryEngine()
    tournament_id = uuid4()
    monkeypatch.setattr(coordination, "engine", engine)

    with pytest.raises(RuntimeError, match="delivery failed"):
        async with coordination.private_tournament_standings_mutex(tournament_id):
            raise RuntimeError("delivery failed")

    async with coordination.private_tournament_standings_mutex(tournament_id):
        assert engine.lock.locked()
    assert not engine.lock.locked()
    assert {
        lock_key for connection in engine.connections for _sql, lock_key in connection.parameters
    } == {f"private-tournament-standings:{tournament_id}"}


@pytest.mark.asyncio
async def test_cancellation_releases_mutex_and_retry_acquires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _AdvisoryEngine()
    tournament_id = uuid4()
    entered = asyncio.Event()
    hold = asyncio.Event()
    monkeypatch.setattr(coordination, "engine", engine)

    async def _owner() -> None:
        async with coordination.private_tournament_standings_mutex(tournament_id):
            entered.set()
            await hold.wait()

    task = asyncio.create_task(_owner())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    async with coordination.private_tournament_standings_mutex(tournament_id):
        assert engine.lock.locked()
    assert not engine.lock.locked()


@pytest.mark.asyncio
async def test_cancellation_during_acquire_discards_connection_and_retry_acquires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _AdvisoryEngine()
    tournament_id = uuid4()
    engine.cancel_next_acquire = True
    monkeypatch.setattr(coordination, "engine", engine)

    with pytest.raises(asyncio.CancelledError):
        async with coordination.private_tournament_standings_mutex(tournament_id):
            pytest.fail("canceled acquire must not enter the mutation section")

    canceled_connection = engine.connections[0]
    assert canceled_connection.invalidated
    assert canceled_connection.closed
    assert not engine.lock.locked()
    async with coordination.private_tournament_standings_mutex(tournament_id):
        assert engine.lock.locked()
    assert not engine.lock.locked()


class _TransitionSession:
    def __init__(self) -> None:
        self.parameters: list[tuple[str, str]] = []

    async def execute(self, statement, params) -> None:
        self.parameters.append((str(statement), params["lock_key"]))


@pytest.mark.asyncio
async def test_lifecycle_and_delivery_use_the_same_advisory_lock_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _AdvisoryEngine()
    session = _TransitionSession()
    tournament_id = uuid4()
    monkeypatch.setattr(coordination, "engine", engine)

    await coordination.lock_standings_phase_transition(
        session,  # type: ignore[arg-type]
        tournament_id=tournament_id,
    )
    async with coordination.private_tournament_standings_mutex(tournament_id):
        pass

    xact_sql, xact_key = session.parameters[0]
    delivery_parameters = engine.connections[0].parameters
    assert "pg_advisory_xact_lock" in xact_sql
    assert "pg_advisory_lock" in delivery_parameters[0][0]
    assert "pg_advisory_unlock" in delivery_parameters[1][0]
    assert {xact_key, *(lock_key for _sql, lock_key in delivery_parameters)} == {
        f"private-tournament-standings:{tournament_id}"
    }
