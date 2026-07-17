from __future__ import annotations

import asyncio
from uuid import uuid4

from app.workers.tasks import daily_cup_messaging, tournaments_messaging
from tests.workers.daily_cup_turn_reminder_test_support import session_local_with_sessions


def test_daily_cup_messaging_returns_empty_when_context_missing(monkeypatch) -> None:
    async def _missing_context(**_kwargs):
        return None

    monkeypatch.setattr(daily_cup_messaging, "SessionLocal", session_local_with_sessions("s"))
    monkeypatch.setattr(
        daily_cup_messaging, "load_daily_cup_round_messaging_context", _missing_context
    )

    result = asyncio.run(
        daily_cup_messaging.run_daily_cup_round_messaging_async_with_followups(
            tournament_id=str(uuid4()),
            enqueue_completion_followups=False,
        )
    )

    assert result == {"processed": 0, "participants_total": 0, "sent": 0, "edited": 0, "failed": 0}


def test_private_tournament_messaging_invalid_and_missing_context(monkeypatch) -> None:
    assert (
        asyncio.run(
            tournaments_messaging.run_private_tournament_round_messaging_async(tournament_id="bad")
        )["processed"]
        == 0
    )

    async def _missing_context(**_kwargs):
        return None

    monkeypatch.setattr(tournaments_messaging, "SessionLocal", session_local_with_sessions("s"))
    monkeypatch.setattr(tournaments_messaging, "load_round_messaging_context", _missing_context)

    result = asyncio.run(
        tournaments_messaging.run_private_tournament_round_messaging_async(
            tournament_id=str(uuid4())
        )
    )

    assert result == {
        "processed": 0,
        "participants_total": 0,
        "sent": 0,
        "edited": 0,
        "failed": 0,
        "skipped": 0,
    }
