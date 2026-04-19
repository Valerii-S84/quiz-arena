from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_EXPIRED
from app.game.sessions.service import friend_challenges_manage_repost
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _challenge(
    *,
    status: str = DUEL_STATUS_EXPIRED,
    creator_user_id: int = 11,
    opponent_user_id: int | None = 22,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        status=status,
        mode_code="QUICK_MIX_A1A2",
        total_rounds=7,
        completed_at=None,
        updated_at=None,
    )


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


@pytest.mark.asyncio
async def test_repost_friend_challenge_as_open_creates_repost_and_emits_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    repost = SimpleNamespace(challenge_id=uuid4(), total_rounds=challenge.total_rounds)
    analytics_events: list[dict[str, object]] = []
    create_calls: list[dict[str, object]] = []

    async def _fake_create_friend_challenge(*_args, **kwargs):
        create_calls.append(kwargs)
        return repost

    async def _fake_emit_analytics_event(*_args, **kwargs) -> None:
        analytics_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_manage_repost,
        "load_manageable_friend_challenge",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage_repost,
        "create_friend_challenge",
        _fake_create_friend_challenge,
    )
    monkeypatch.setattr(
        friend_challenges_manage_repost,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )

    result = await friend_challenges_manage_repost.repost_friend_challenge_as_open(
        _Session(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result is repost
    assert create_calls == [
        {
            "creator_user_id": 11,
            "mode_code": challenge.mode_code,
            "now_utc": NOW_UTC,
            "challenge_type": friend_challenges_manage_repost.DUEL_TYPE_OPEN,
            "total_rounds": challenge.total_rounds,
        }
    ]
    assert analytics_events == [
        {
            "event_type": "duel_reposted_as_open",
            "source": friend_challenges_manage_repost.EVENT_SOURCE_BOT,
            "happened_at": NOW_UTC,
            "user_id": 11,
            "payload": {
                "source_challenge_id": str(challenge.id),
                "repost_challenge_id": str(repost.challenge_id),
                "format": repost.total_rounds,
            },
        }
    ]


@pytest.mark.asyncio
async def test_repost_friend_challenge_as_open_delegates_state_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    repost = SimpleNamespace(challenge_id=uuid4(), total_rounds=challenge.total_rounds)
    calls: list[dict[str, object]] = []

    async def _fake_load_manageable_friend_challenge(*_args, **kwargs):
        calls.append(kwargs)
        return challenge

    monkeypatch.setattr(
        friend_challenges_manage_repost,
        "load_manageable_friend_challenge",
        _fake_load_manageable_friend_challenge,
    )
    monkeypatch.setattr(
        friend_challenges_manage_repost,
        "create_friend_challenge",
        _async_return(repost),
    )
    monkeypatch.setattr(
        friend_challenges_manage_repost,
        "emit_analytics_event",
        _async_return(None),
    )

    await friend_challenges_manage_repost.repost_friend_challenge_as_open(
        _Session(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert calls == [
        {
            "challenge_id": challenge.id,
            "user_id": 11,
            "now_utc": NOW_UTC,
        }
    ]
