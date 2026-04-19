from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.game.sessions.service import friend_challenges_join_analytics
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
SERIES_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_emit_friend_challenge_joined_events_emits_join_and_accept_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(
        creator_user_id=11,
        mode_code="QUICK_MIX_A1A2",
        total_rounds=7,
        challenge_type="DIRECT",
        expires_at=NOW_UTC + timedelta(hours=6),
        series_id=SERIES_ID,
        series_game_number=2,
        series_best_of=3,
    )
    analytics_events: list[dict[str, object]] = []

    async def _fake_emit_analytics_event(*_args, **kwargs) -> None:
        analytics_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_join_analytics,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )

    await friend_challenges_join_analytics.emit_friend_challenge_joined_events(
        _Session(),
        challenge=challenge,
        happened_at=NOW_UTC,
        source="bot",
        user_id=22,
    )

    assert analytics_events == [
        {
            "event_type": "friend_challenge_joined",
            "source": "bot",
            "happened_at": NOW_UTC,
            "user_id": 22,
            "payload": {
                "challenge_id": str(challenge.id),
                "creator_user_id": 11,
                "mode_code": "QUICK_MIX_A1A2",
                "total_rounds": 7,
                "expires_at": challenge.expires_at.isoformat(),
                "series_id": str(SERIES_ID),
                "series_game_number": 2,
                "series_best_of": 3,
            },
        },
        {
            "event_type": "duel_accepted",
            "source": "bot",
            "happened_at": NOW_UTC,
            "user_id": 22,
            "payload": {
                "challenge_id": str(challenge.id),
                "challenge_type": "DIRECT",
                "format": 7,
            },
        },
    ]
