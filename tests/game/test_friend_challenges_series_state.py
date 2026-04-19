from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.game.sessions.service import (
    friend_challenges_followup_state,
    friend_challenges_series_state,
)
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_load_friend_challenge_series_context_delegates_to_followup_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge()
    context = friend_challenges_followup_state.FriendChallengeFollowupContext(
        challenge=challenge,
        opponent_user_id=202,
    )
    captured_kwargs: dict[str, object] = {}

    async def _fake_load_followup_context(session, **kwargs):
        captured_kwargs["session"] = session
        captured_kwargs.update(kwargs)
        return context

    monkeypatch.setattr(
        friend_challenges_series_state.friend_challenges_followup_state,
        "load_friend_challenge_followup_context",
        _fake_load_followup_context,
    )

    session = _Session()
    result = await friend_challenges_series_state.load_friend_challenge_series_context(
        session,
        initiator_user_id=101,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == context
    assert captured_kwargs == {
        "session": session,
        "challenge_id": challenge.id,
        "initiator_user_id": 101,
        "now_utc": NOW_UTC,
    }
