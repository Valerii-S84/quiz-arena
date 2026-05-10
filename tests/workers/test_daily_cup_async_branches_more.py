from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.workers.tasks import daily_cup_async, daily_cup_core
from tests.workers.daily_cup_turn_reminder_test_support import session_local_with_sessions


def test_publish_daily_cup_final_results_sends_followups(monkeypatch) -> None:
    tournament_id = uuid4()
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: datetime.now(timezone.utc))
    monkeypatch.setattr(daily_cup_async, "SessionLocal", session_local_with_sessions("session"))
    monkeypatch.setattr(
        daily_cup_async.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        lambda *_args, **_kwargs: _async_value(
            SimpleNamespace(id=tournament_id, status="COMPLETED")
        ),
    )
    monkeypatch.setattr(
        daily_cup_async,
        "run_daily_cup_round_messaging_async_with_followups",
        lambda **_kwargs: _async_value({"processed": 1}),
    )

    result = asyncio.run(daily_cup_async.publish_daily_cup_final_results_async())

    assert result == {"processed": 1, "published": 1}


def test_close_daily_cup_registration_starts_and_enqueues(monkeypatch) -> None:
    tournament_id = uuid4()
    tournament = SimpleNamespace(id=tournament_id, status="REGISTRATION")
    participants = [SimpleNamespace(user_id=1), SimpleNamespace(user_id=2)]
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: datetime.now(timezone.utc))
    monkeypatch.setattr(daily_cup_async, "DAILY_CUP_MIN_PARTICIPANTS", 2)
    monkeypatch.setattr(daily_cup_async, "SessionLocal", session_local_with_sessions("session"))
    monkeypatch.setattr(
        daily_cup_async,
        "ensure_daily_cup_registration_tournament",
        lambda **_kwargs: _async_value(tournament),
    )
    monkeypatch.setattr(
        daily_cup_async.TournamentParticipantsRepo,
        "list_for_tournament_for_update",
        lambda *_args, **_kwargs: _async_value(participants),
    )
    monkeypatch.setattr(
        daily_cup_async,
        "start_daily_arena_round_one",
        lambda *_args, **_kwargs: _async_call(calls, "start", len(participants)),
    )
    monkeypatch.setattr(
        daily_cup_async,
        "emit_daily_cup_events",
        lambda **kwargs: _async_call(calls, "events", len(kwargs["events"])),
    )
    monkeypatch.setattr(
        daily_cup_async,
        "send_daily_cup_canceled_messages",
        lambda **kwargs: _async_call(calls, "canceled", kwargs["telegram_targets"]),
    )
    monkeypatch.setattr(
        daily_cup_async,
        "enqueue_daily_cup_round_messaging",
        lambda **kwargs: calls.append(("enqueue", kwargs["tournament_id"])),
    )

    result = asyncio.run(daily_cup_async.close_daily_cup_registration_and_start_async())

    assert result["started"] == 1
    assert ("start", 2) in calls
    assert ("events", 2) in calls
    assert ("enqueue", str(tournament_id)) in calls


def test_ensure_daily_cup_registration_tournament_returns_existing(monkeypatch) -> None:
    existing = SimpleNamespace(id=uuid4())
    session = SimpleNamespace(execute=lambda *_args, **_kwargs: _async_value(None))
    monkeypatch.setattr(
        daily_cup_core.TournamentsRepo,
        "get_by_type_and_registration_deadline_for_update",
        lambda *_args, **_kwargs: _async_value(existing),
    )

    result = asyncio.run(
        daily_cup_core.ensure_daily_cup_registration_tournament(
            session=session,
            now_utc_value=datetime.now(timezone.utc),
        )
    )

    assert result is existing


async def _async_value(value):
    return value


async def _async_call(calls: list[tuple[str, object]], name: str, value: object) -> None:
    calls.append((name, value))
