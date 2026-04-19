from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.game.sessions.service import friend_challenges_create_seed_state
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
CHALLENGE_ID = UUID("11111111-1111-1111-1111-111111111111")


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


@pytest.mark.asyncio
async def test_load_friend_challenge_create_seed_state_resolves_access_and_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_question_kwargs: dict[str, object] = {}

    async def _fake_select_duel_question_ids(*args, **kwargs):
        del args
        captured_question_kwargs.update(kwargs)
        return ["q-1", "q-2", "q-3"]

    monkeypatch.setattr(friend_challenges_create_seed_state, "uuid4", lambda: CHALLENGE_ID)
    monkeypatch.setattr(
        friend_challenges_create_seed_state,
        "_resolve_friend_challenge_access_type",
        _async_return("FREE"),
    )
    monkeypatch.setattr(
        friend_challenges_create_seed_state,
        "select_duel_question_ids",
        _fake_select_duel_question_ids,
    )

    state = await friend_challenges_create_seed_state.load_friend_challenge_create_seed_state(
        _Session(),
        creator_user_id=101,
        mode_code="QUICK_MIX_A1A2",
        total_rounds=3,
        now_utc=NOW_UTC,
    )

    assert state == friend_challenges_create_seed_state.FriendChallengeCreateSeedState(
        challenge_id=CHALLENGE_ID,
        access_type="FREE",
        question_ids=["q-1", "q-2", "q-3"],
    )
    assert captured_question_kwargs == {
        "mode_code": "QUICK_MIX_A1A2",
        "total_rounds": 3,
        "now_utc": NOW_UTC,
        "challenge_seed": str(CHALLENGE_ID),
    }
