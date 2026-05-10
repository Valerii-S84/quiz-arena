from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.workers.tasks import tournaments_async
from tests.workers.payments_reliability_async_support import SessionLocalStub


@pytest.mark.asyncio
async def test_emit_round_events_skips_empty_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _unexpected_event(*_args, **_kwargs) -> None:
        pytest.fail("no event should be emitted for empty tournament id batches")

    monkeypatch.setattr(tournaments_async, "emit_analytics_event", _unexpected_event)

    await tournaments_async._emit_round_events(
        now_utc=tournaments_async.datetime.now(tournaments_async.timezone.utc),
        started_tournament_ids=[],
        completed_tournament_ids=[],
    )


@pytest.mark.asyncio
async def test_run_private_tournament_rounds_processes_due_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = SimpleNamespace(id=uuid4(), status="ROUND_1", current_round=1)
    completed = SimpleNamespace(id=uuid4(), status="COMPLETED", current_round=4)
    enqueued_rounds: list[str] = []
    enqueued_cards: list[str] = []
    events: list[dict[str, object]] = []

    monkeypatch.setattr(tournaments_async, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        tournaments_async.TournamentsRepo,
        "list_due_registration_close_for_update",
        _async_return([SimpleNamespace(id=uuid4(), status="REGISTRATION")]),
    )
    monkeypatch.setattr(
        tournaments_async.TournamentsRepo,
        "list_due_round_deadline_for_update",
        _async_return([started, completed]),
    )
    monkeypatch.setattr(tournaments_async, "close_expired_registration", _async_return(True))

    async def _settle(_session, *, tournament, **_kwargs) -> dict[str, int]:
        if tournament is started:
            return _transition(round_started=1, matches_settled=2, matches_created=2)
        return _transition(tournament_completed=1, matches_settled=1)

    async def _emit(_session, **kwargs) -> None:
        events.append(kwargs)

    monkeypatch.setattr(tournaments_async, "settle_round_and_advance", _settle)
    monkeypatch.setattr(tournaments_async, "emit_analytics_event", _emit)
    monkeypatch.setattr(
        tournaments_async,
        "enqueue_private_tournament_round_messaging",
        lambda *, tournament_id: enqueued_rounds.append(tournament_id),
    )
    monkeypatch.setattr(
        tournaments_async,
        "enqueue_private_tournament_proof_cards",
        lambda *, tournament_id: enqueued_cards.append(tournament_id),
    )

    result = await tournaments_async.run_private_tournament_rounds_async(
        batch_size=0,
        round_duration_hours=2,
    )

    assert result["batch_size"] == 1
    assert result["registration_closed_total"] == 1
    assert result["rounds_started_total"] == 1
    assert result["tournaments_completed_total"] == 1
    assert result["round_messages_enqueued_total"] == 2
    assert result["proof_cards_enqueued_total"] == 1
    assert enqueued_rounds == [str(started.id), str(completed.id)]
    assert enqueued_cards == [str(completed.id)]
    assert {event["event_type"] for event in events} == {
        "private_tournament_round_started",
        "private_tournament_completed",
    }


def _transition(
    *,
    round_started: int = 0,
    tournament_completed: int = 0,
    matches_settled: int = 0,
    matches_created: int = 0,
) -> dict[str, int]:
    return {
        "round_started": round_started,
        "tournament_completed": tournament_completed,
        "matches_settled": matches_settled,
        "matches_created": matches_created,
    }


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
