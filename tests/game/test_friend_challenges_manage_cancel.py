from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_CANCELED, DUEL_STATUS_EXPIRED
from app.game.sessions.service import friend_challenges_manage_cancel
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
async def test_cancel_friend_challenge_by_creator_marks_canceled_and_returns_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    analytics_events: list[dict[str, object]] = []
    snapshot = {"challenge_id": str(challenge.id), "status": DUEL_STATUS_CANCELED}

    async def _fake_emit_analytics_event(*_args, **kwargs) -> None:
        analytics_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_manage_cancel,
        "load_manageable_friend_challenge",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage_cancel,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )
    monkeypatch.setattr(
        friend_challenges_manage_cancel,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: snapshot if challenge_row is challenge else None,
    )

    result = await friend_challenges_manage_cancel.cancel_friend_challenge_by_creator(
        _Session(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == snapshot
    assert challenge.status == DUEL_STATUS_CANCELED
    assert challenge.completed_at == NOW_UTC
    assert challenge.updated_at == NOW_UTC
    assert analytics_events == [
        {
            "event_type": "duel_canceled_by_creator",
            "source": friend_challenges_manage_cancel.EVENT_SOURCE_BOT,
            "happened_at": NOW_UTC,
            "user_id": 11,
            "payload": {
                "challenge_id": str(challenge.id),
                "format": challenge.total_rounds,
            },
        }
    ]


@pytest.mark.asyncio
async def test_cancel_friend_challenge_by_creator_delegates_state_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    calls: list[dict[str, object]] = []

    async def _fake_load_manageable_friend_challenge(*_args, **kwargs):
        calls.append(kwargs)
        return challenge

    monkeypatch.setattr(
        friend_challenges_manage_cancel,
        "load_manageable_friend_challenge",
        _fake_load_manageable_friend_challenge,
    )
    monkeypatch.setattr(
        friend_challenges_manage_cancel,
        "emit_analytics_event",
        _async_return(None),
    )
    monkeypatch.setattr(
        friend_challenges_manage_cancel,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: {"challenge_id": str(challenge_row.id)},
    )

    await friend_challenges_manage_cancel.cancel_friend_challenge_by_creator(
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
