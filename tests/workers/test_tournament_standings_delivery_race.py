from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app.workers.tasks import tournaments_message_delivery_persistence, tournaments_messaging
from app.workers.tasks.tournaments_messaging_delivery import TournamentRoundDeliveryResult
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


class _SessionLocal:
    @staticmethod
    def begin() -> AsyncBeginContext[object]:
        return AsyncBeginContext(object())


def _context(
    tournament_id: UUID,
    *,
    round_no: int,
    message_id: int | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        parsed_tournament_id=tournament_id,
        tournament=SimpleNamespace(status=f"ROUND_{round_no}", current_round=round_no),
        standings_user_ids=[11],
        participant_rows={11: SimpleNamespace(standings_message_id=message_id)},
    )


class _TaskMutex:
    def __init__(self, *, blocked_task: str | None = None) -> None:
        self._lock = asyncio.Lock()
        self._blocked_task = blocked_task
        self.release_blocked = asyncio.Event()

    @asynccontextmanager
    async def __call__(self, _tournament_id: UUID):
        task = asyncio.current_task()
        if task is not None and task.get_name() == self._blocked_task:
            await self.release_blocked.wait()
        async with self._lock:
            yield


@pytest.mark.asyncio
async def test_stale_round_waiting_for_mutex_does_not_edit_after_new_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament_id = uuid4()
    state: dict[str, int | None] = {"round": 1, "message_id": 101}
    first_round_loaded = asyncio.Event()
    load_counts: dict[str, int] = {}
    deliveries: list[tuple[int, int | None]] = []
    mutex = _TaskMutex(blocked_task="round-1")

    async def _load(*_args, **_kwargs):
        task = asyncio.current_task()
        task_name = task.get_name() if task is not None else "unknown"
        load_counts[task_name] = load_counts.get(task_name, 0) + 1
        snapshot = _context(
            tournament_id,
            round_no=int(state["round"] or 0),
            message_id=state["message_id"],
        )
        if task_name == "round-1" and load_counts[task_name] == 1:
            first_round_loaded.set()
        return snapshot

    async def _deliver(*, context, **_kwargs):
        round_no = int(context.tournament.current_round)
        message_id = context.participant_rows[11].standings_message_id
        deliveries.append((round_no, message_id))
        state["message_id"] = 202
        return TournamentRoundDeliveryResult(0, 1, 0, 0, {}, {})

    monkeypatch.setattr(tournaments_messaging, "SessionLocal", _SessionLocal)
    monkeypatch.setattr(tournaments_messaging, "load_round_messaging_context", _load)
    monkeypatch.setattr(tournaments_messaging, "deliver_round_messages", _deliver)
    monkeypatch.setattr(tournaments_messaging, "private_tournament_standings_mutex", mutex)

    stale_task = asyncio.create_task(
        tournaments_messaging.run_private_tournament_round_messaging_async(
            tournament_id=str(tournament_id)
        ),
        name="round-1",
    )
    await first_round_loaded.wait()
    state["round"] = 2
    fresh_result = await tournaments_messaging.run_private_tournament_round_messaging_async(
        tournament_id=str(tournament_id)
    )
    mutex.release_blocked.set()
    stale_result = await stale_task

    assert deliveries == [(2, 101)]
    assert fresh_result["edited"] == 1
    assert stale_result == tournaments_messaging._empty_round_messaging_result()
    assert state["message_id"] == 202


@pytest.mark.asyncio
async def test_concurrent_initial_snapshots_send_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament_id = uuid4()
    state: dict[str, int | None] = {"message_id": None}
    initial_loads_complete = asyncio.Event()
    initial_load_count = 0
    task_load_counts: dict[str, int] = {}
    sends: list[int] = []
    edits: list[int] = []
    mutex = _TaskMutex()

    async def _load(*_args, **_kwargs):
        nonlocal initial_load_count
        task = asyncio.current_task()
        task_name = task.get_name() if task is not None else "unknown"
        task_load_counts[task_name] = task_load_counts.get(task_name, 0) + 1
        snapshot = _context(tournament_id, round_no=1, message_id=state["message_id"])
        if task_load_counts[task_name] == 1:
            initial_load_count += 1
            if initial_load_count == 2:
                initial_loads_complete.set()
            await initial_loads_complete.wait()
        return snapshot

    async def _deliver(*, context, **_kwargs):
        if context.participant_rows[11].standings_message_id is None:
            sends.append(501)
            state["message_id"] = 501
            return TournamentRoundDeliveryResult(1, 0, 0, 0, {11: 501}, {})
        edits.append(int(context.participant_rows[11].standings_message_id))
        return TournamentRoundDeliveryResult(0, 1, 0, 0, {}, {})

    monkeypatch.setattr(tournaments_messaging, "SessionLocal", _SessionLocal)
    monkeypatch.setattr(tournaments_messaging, "load_round_messaging_context", _load)
    monkeypatch.setattr(tournaments_messaging, "deliver_round_messages", _deliver)
    monkeypatch.setattr(tournaments_messaging, "private_tournament_standings_mutex", mutex)

    results = await asyncio.gather(
        asyncio.create_task(
            tournaments_messaging.run_private_tournament_round_messaging_async(
                tournament_id=str(tournament_id)
            ),
            name="initial-a",
        ),
        asyncio.create_task(
            tournaments_messaging.run_private_tournament_round_messaging_async(
                tournament_id=str(tournament_id)
            ),
            name="initial-b",
        ),
    )

    assert sends == [501]
    assert edits == [501]
    assert state["message_id"] == 501
    assert sum(result["sent"] for result in results) == 1


class _PersistenceSessionLocal:
    @staticmethod
    def begin() -> AsyncBeginContext[object]:
        return AsyncBeginContext(object())


async def _assert_stale_fence_does_not_mark_sent(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authoritative_message_id: int,
    authoritative_status: str,
    authoritative_round: int,
    expected_message_id: int,
    expected_status: str,
    expected_round: int,
) -> None:
    terminal_calls: list[str] = []
    pointer = {"message_id": authoritative_message_id}

    async def _compare_and_set(_session, **kwargs) -> int:
        is_current = (
            pointer["message_id"] == kwargs["expected_message_id"]
            and authoritative_status == kwargs["expected_status"]
            and authoritative_round == kwargs["expected_round"]
        )
        if is_current:
            pointer["message_id"] = kwargs["message_id"]
        return int(is_current)

    async def _mark_sent(*_args, **_kwargs) -> int:
        terminal_calls.append("sent")
        return 1

    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TournamentParticipantsRepo,
        "compare_and_set_standings_message_id",
        _compare_and_set,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "mark_sent",
        _mark_sent,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence,
        "SessionLocal",
        _PersistenceSessionLocal,
    )

    with pytest.raises(RuntimeError, match="standings delivery fence was lost"):
        await tournaments_message_delivery_persistence.persist_private_tournament_sent_message(
            cast(Any, SimpleNamespace(idempotency_key="stale")),
            tournaments_message_delivery_persistence.PrivateTournamentStandingsFence(
                tournament_id=uuid4(),
                user_id=11,
                expected_message_id=expected_message_id,
                expected_status=expected_status,
                expected_round=expected_round,
            ),
            777,
            NOW_UTC,
        )

    assert pointer["message_id"] == authoritative_message_id
    assert terminal_calls == []


@pytest.mark.asyncio
async def test_stale_task_does_not_overwrite_newer_message_pointer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _assert_stale_fence_does_not_mark_sent(
        monkeypatch,
        authoritative_message_id=902,
        authoritative_status="ROUND_2",
        authoritative_round=2,
        expected_message_id=222,
        expected_status="ROUND_2",
        expected_round=2,
    )


@pytest.mark.asyncio
async def test_stale_generation_does_not_mark_terminal_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _assert_stale_fence_does_not_mark_sent(
        monkeypatch,
        authoritative_message_id=902,
        authoritative_status="ROUND_2",
        authoritative_round=2,
        expected_message_id=902,
        expected_status="ROUND_1",
        expected_round=1,
    )
