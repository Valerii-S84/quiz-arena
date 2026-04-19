from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.sessions.service import friend_challenges_manage
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_repost_friend_challenge_as_open_delegates_to_manage_repost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repost = SimpleNamespace(challenge_id=uuid4(), total_rounds=7)
    captured_kwargs: dict[str, object] = {}
    session = _Session()

    async def _fake_manage_repost_friend_challenge_as_open(session, **kwargs):
        captured_kwargs["session"] = session
        captured_kwargs.update(kwargs)
        return repost

    monkeypatch.setattr(
        friend_challenges_manage,
        "manage_repost_friend_challenge_as_open",
        _fake_manage_repost_friend_challenge_as_open,
    )

    result = await friend_challenges_manage.repost_friend_challenge_as_open(
        session,
        user_id=11,
        challenge_id=repost.challenge_id,
        now_utc=NOW_UTC,
    )

    assert result is repost
    assert captured_kwargs == {
        "session": session,
        "user_id": 11,
        "challenge_id": repost.challenge_id,
        "now_utc": NOW_UTC,
    }


@pytest.mark.asyncio
async def test_cancel_friend_challenge_by_creator_delegates_to_manage_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = {"challenge_id": str(uuid4())}
    captured_kwargs: dict[str, object] = {}
    challenge_id = uuid4()
    session = _Session()

    async def _fake_manage_cancel_friend_challenge_by_creator(session, **kwargs):
        captured_kwargs["session"] = session
        captured_kwargs.update(kwargs)
        return snapshot

    monkeypatch.setattr(
        friend_challenges_manage,
        "manage_cancel_friend_challenge_by_creator",
        _fake_manage_cancel_friend_challenge_by_creator,
    )

    result = await friend_challenges_manage.cancel_friend_challenge_by_creator(
        session,
        user_id=11,
        challenge_id=challenge_id,
        now_utc=NOW_UTC,
    )

    assert result is snapshot
    assert captured_kwargs == {
        "session": session,
        "user_id": 11,
        "challenge_id": challenge_id,
        "now_utc": NOW_UTC,
    }
