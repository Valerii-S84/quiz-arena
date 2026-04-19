from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.game.sessions.service import friend_challenges_create
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
CHALLENGE_ID = UUID("11111111-1111-1111-1111-111111111111")


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_create_friend_challenge_delegates_to_standard_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = {"challenge_id": str(CHALLENGE_ID)}
    session = _Session()
    captured_kwargs: dict[str, object] = {}

    async def _fake_create_standard_friend_challenge(session, **kwargs):
        captured_kwargs["session"] = session
        captured_kwargs.update(kwargs)
        return snapshot

    monkeypatch.setattr(
        friend_challenges_create,
        "create_standard_friend_challenge",
        _fake_create_standard_friend_challenge,
    )

    result = await friend_challenges_create.create_friend_challenge(
        session,
        creator_user_id=101,
        mode_code="QUICK_MIX_A1A2",
        now_utc=NOW_UTC,
    )

    assert result is snapshot
    assert captured_kwargs == {
        "session": session,
        "creator_user_id": 101,
        "mode_code": "QUICK_MIX_A1A2",
        "now_utc": NOW_UTC,
        "challenge_type": "DIRECT",
        "total_rounds": friend_challenges_create.FRIEND_CHALLENGE_TOTAL_ROUNDS,
    }


@pytest.mark.asyncio
async def test_create_friend_challenge_rematch_delegates_to_rematch_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = {"challenge_id": str(CHALLENGE_ID)}
    session = _Session()
    captured_kwargs: dict[str, object] = {}

    async def _fake_create_rematch_friend_challenge(session, **kwargs):
        captured_kwargs["session"] = session
        captured_kwargs.update(kwargs)
        return snapshot

    monkeypatch.setattr(
        friend_challenges_create,
        "create_rematch_friend_challenge",
        _fake_create_rematch_friend_challenge,
    )

    result = await friend_challenges_create.create_friend_challenge_rematch(
        session,
        initiator_user_id=202,
        challenge_id=CHALLENGE_ID,
        now_utc=NOW_UTC,
    )

    assert result is snapshot
    assert captured_kwargs == {
        "session": session,
        "initiator_user_id": 202,
        "challenge_id": CHALLENGE_ID,
        "now_utc": NOW_UTC,
    }
