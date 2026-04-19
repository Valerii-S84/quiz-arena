from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app.game.sessions.service import friend_challenges_create_standard_analytics
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
SERIES_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class _Session(AsyncSessionStub):
    pass


def _duel(
    *,
    duel_id: UUID | None = None,
    challenge_type: str = "DIRECT",
    series_id: UUID | None = SERIES_ID,
    series_game_number: int = 1,
    series_best_of: int = 3,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=duel_id or uuid4(),
        mode_code="QUICK_MIX_A1A2",
        challenge_type=challenge_type,
        access_type="FREE",
        total_rounds=7,
        series_id=series_id,
        series_game_number=series_game_number,
        series_best_of=series_best_of,
        expires_at=NOW_UTC + timedelta(minutes=15),
    )


@pytest.mark.asyncio
async def test_emit_standard_duel_created_events_emits_expected_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _duel(series_id=None)
    analytics_events: list[dict[str, Any]] = []

    async def _fake_emit_analytics_event(session, **kwargs):
        del session
        analytics_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_create_standard_analytics,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )

    await friend_challenges_create_standard_analytics.emit_standard_duel_created_events(
        _Session(),
        challenge=cast(Any, challenge),
        happened_at=NOW_UTC,
        source="BOT",
        creator_user_id=101,
    )

    assert [event["event_type"] for event in analytics_events] == [
        "friend_challenge_created",
        "duel_created",
    ]
    assert analytics_events[0]["payload"]["entrypoint"] == "standard"
    assert analytics_events[0]["payload"]["series_id"] is None
    assert analytics_events[1]["payload"]["type"] == challenge.challenge_type
