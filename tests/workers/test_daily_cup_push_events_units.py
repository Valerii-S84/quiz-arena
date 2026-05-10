from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from app.workers.tasks import daily_cup_push_events as events
from tests.workers.payments_reliability_async_support import SessionLocalStub


def test_list_already_pushed_user_ids_delegates_to_repo(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    async def _list(_session, **kwargs):
        calls.append(kwargs)
        return {1, 3}

    monkeypatch.setattr(events, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(events.AnalyticsRepo, "list_user_ids_by_event_type_and_tournament", _list)

    result = asyncio.run(
        events.list_already_pushed_user_ids(
            event_type="daily_push",
            tournament_id="cup-1",
            user_ids=[1, 2, 3],
        )
    )

    assert result == {1, 3}
    assert calls == [
        {
            "event_type": "daily_push",
            "tournament_id": "cup-1",
            "user_ids": [1, 2, 3],
        }
    ]


def test_store_push_sent_events_skips_empty_user_list(monkeypatch) -> None:
    monkeypatch.setattr(
        events,
        "emit_analytics_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected event")),
    )

    asyncio.run(
        events.store_push_sent_events(
            event_type="daily_push",
            tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            user_ids=[],
            happened_at=datetime(2026, 5, 10, 12, 0, tzinfo=UTC),
        )
    )


def test_store_push_sent_events_emits_one_event_per_user(monkeypatch) -> None:
    emitted: list[dict[str, object]] = []

    async def _emit(_session, **kwargs) -> None:
        emitted.append(kwargs)

    tournament_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    happened_at = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(events, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(events, "emit_analytics_event", _emit)

    asyncio.run(
        events.store_push_sent_events(
            event_type="daily_push",
            tournament_id=tournament_id,
            user_ids=[10, 20],
            happened_at=happened_at,
        )
    )

    assert [item["user_id"] for item in emitted] == [10, 20]
    assert emitted[0]["payload"] == {"tournament_id": str(tournament_id)}
    assert emitted[0]["source"] == events.EVENT_SOURCE_WORKER
