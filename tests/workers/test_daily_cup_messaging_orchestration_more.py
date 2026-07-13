from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.workers.tasks import daily_cup_messaging
from tests.workers.daily_cup_turn_reminder_test_support import session_local_with_sessions


class _Bot:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self.calls = calls
        self.session = SimpleNamespace(close=self._close)
        self.closed = False

    async def _close(self) -> None:
        self.closed = True
        self.calls.append(("close", True))


def test_run_daily_cup_round_messaging_async_delivers_closes_and_follows_up(monkeypatch) -> None:
    tournament_id = uuid4()
    calls: list[tuple[str, object]] = []
    bot = _Bot(calls)
    context = SimpleNamespace(
        parsed_tournament_id=tournament_id,
        tournament="tournament",
        round_matches=["match"],
        standings_user_ids=[1],
        labels={1: "Ada"},
        telegram_targets={1: 10},
        points_by_user={1: "7"},
        tie_breaks_by_user={1: "1"},
        place_by_user={1: 1},
        participant_rows={1: object()},
        participants_total=1,
        is_completed=True,
        allow_completion_followups=True,
        registration_deadline=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    async def _load_context(**kwargs):
        calls.append(("session", kwargs["session"]))
        return context

    async def _deliver(**kwargs):
        calls.append(("deliver", kwargs["bot"]))
        return {
            "sent": 2,
            "edited": 1,
            "failed": 0,
            "new_message_ids": {1: 11},
            "replaced_message_ids": {2: 22},
        }

    monkeypatch.setattr(daily_cup_messaging, "SessionLocal", session_local_with_sessions("s1"))
    monkeypatch.setattr(
        daily_cup_messaging, "load_daily_cup_round_messaging_context", _load_context
    )
    monkeypatch.setattr(daily_cup_messaging, "deliver_daily_cup_messages", _deliver)
    monkeypatch.setattr(daily_cup_messaging, "build_bot", lambda: bot)
    monkeypatch.setattr(
        daily_cup_messaging,
        "handle_daily_cup_completion_followups",
        lambda **kwargs: calls.append(("followups", kwargs["enqueue_completion_followups"])),
    )

    result = asyncio.run(
        daily_cup_messaging.run_daily_cup_round_messaging_async_with_followups(
            tournament_id=str(tournament_id),
            enqueue_completion_followups=True,
        )
    )

    assert result == {
        "processed": 1,
        "participants_total": 1,
        "sent": 2,
        "edited": 1,
        "failed": 0,
        "skipped": 0,
    }
    assert bot.closed is True
    assert calls == [
        ("session", "s1"),
        ("deliver", bot),
        ("close", True),
        ("followups", True),
    ]


def test_enqueue_daily_cup_round_messaging_fallback_and_warning(monkeypatch) -> None:
    coros: list[object] = []
    warnings: list[dict[str, object]] = []

    def _run(coro) -> None:
        coros.append(coro)
        coro.close()

    monkeypatch.setattr(daily_cup_messaging, "is_celery_task", lambda _task: False)
    monkeypatch.setattr(daily_cup_messaging, "run_async_job", _run)
    daily_cup_messaging.enqueue_daily_cup_round_messaging(tournament_id="tid")
    assert len(coros) == 1

    def _raise_after_close(coro) -> None:
        coro.close()
        raise RuntimeError("x")

    monkeypatch.setattr(daily_cup_messaging, "run_async_job", _raise_after_close)
    monkeypatch.setattr(
        daily_cup_messaging,
        "logger",
        SimpleNamespace(
            warning=lambda event, **kwargs: warnings.append({"event": event, **kwargs})
        ),
    )
    daily_cup_messaging.enqueue_daily_cup_round_messaging(tournament_id="tid")

    assert warnings[0]["event"] == "daily_cup_round_message_enqueue_failed"
    assert warnings[0]["error_type"] == "RuntimeError"
