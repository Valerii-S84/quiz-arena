from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.workers.tasks import daily_cup_core, daily_cup_rounds, daily_cup_task_helpers
from tests.workers.daily_cup_turn_reminder_test_support import session_local_with_sessions


def test_advance_daily_cup_rounds_async_emits_followups_and_logs(monkeypatch) -> None:
    outcome = SimpleNamespace(
        events=[{"event_type": "daily_cup_started", "payload": {"x": 1}}],
        walkover_notifications=["walkover"],
        completed_ids=["tid"],
        rounds_started_total=1,
        tournaments_completed_total=1,
        matches_settled_total=2,
        matches_created_total=3,
    )
    calls: list[tuple[str, object]] = []

    async def _advance(**kwargs):
        calls.append(("advance", kwargs["session"]))
        return outcome

    async def _emit(**kwargs):
        calls.append(("events", kwargs["events"]))

    async def _walkovers(**kwargs):
        calls.append(("walkovers", kwargs["notifications"]))

    monkeypatch.setattr(daily_cup_rounds, "SessionLocal", session_local_with_sessions("session"))
    monkeypatch.setattr(daily_cup_rounds, "advance_due_daily_cup_rounds", _advance)
    monkeypatch.setattr(daily_cup_rounds, "emit_daily_cup_events", _emit)
    monkeypatch.setattr(daily_cup_rounds, "send_daily_cup_walkover_notifications", _walkovers)
    monkeypatch.setattr(
        daily_cup_rounds,
        "enqueue_daily_cup_completion_messaging",
        lambda **kwargs: calls.append(("completed", kwargs["tournament_ids"])),
    )
    monkeypatch.setattr(
        daily_cup_rounds,
        "logger",
        SimpleNamespace(info=lambda event, **kwargs: calls.append((event, kwargs))),
    )

    result = asyncio.run(daily_cup_rounds.advance_daily_cup_rounds_async())

    assert result["rounds_started_total"] == 1
    assert ("advance", "session") in calls
    assert ("events", outcome.events) in calls
    assert ("walkovers", ["walkover"]) in calls
    assert ("completed", ["tid"]) in calls


def test_daily_cup_core_emit_and_persist_use_session(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    tournament_id = uuid4()

    async def _emit(_session, **kwargs):
        calls.append(("emit", kwargs["event_type"]))

    async def _missing(_session, **kwargs):
        calls.append(("missing", kwargs["message_id"]))

    async def _replace(_session, **kwargs):
        calls.append(("replace", kwargs["message_id"]))

    monkeypatch.setattr(daily_cup_core, "SessionLocal", session_local_with_sessions("s1", "s2"))
    monkeypatch.setattr(daily_cup_core, "emit_analytics_event", _emit)
    monkeypatch.setattr(
        daily_cup_core.TournamentParticipantsRepo, "set_standings_message_id_if_missing", _missing
    )
    monkeypatch.setattr(
        daily_cup_core.TournamentParticipantsRepo, "set_standings_message_id", _replace
    )

    asyncio.run(
        daily_cup_core.emit_daily_cup_events(
            now_utc_value=datetime.now(timezone.utc),
            events=[
                {"event_type": "a", "payload": {"v": 1}},
                {"event_type": "b", "payload": "bad"},
            ],
        )
    )
    asyncio.run(
        daily_cup_core.persist_daily_cup_standings_message_ids(
            tournament_id=tournament_id,
            new_message_ids={1: 10},
            replaced_message_ids={2: 20},
        )
    )

    assert calls == [("emit", "a"), ("emit", "b"), ("missing", 10), ("replace", 20)]


def test_daily_cup_task_helpers_cover_celery_detection_and_date_check() -> None:
    CeleryLike = type("CeleryLike", (), {})
    CeleryLike.__module__ = "celery.app.task"

    assert daily_cup_task_helpers.is_celery_task(CeleryLike()) is True
    assert daily_cup_task_helpers.is_celery_task(object()) is False
    assert daily_cup_task_helpers.is_today_daily_cup_tournament(
        registration_deadline=datetime(2026, 1, 1, 23, tzinfo=timezone.utc),
        now_utc=datetime(2026, 1, 2, 1, tzinfo=timezone.utc),
        timezone_name="Europe/Berlin",
    )
