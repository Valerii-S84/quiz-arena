from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.game.sessions.service import friend_challenges_series
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
SERIES_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SERIES_C_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_create_friend_challenge_best_of_three_delegates_to_series_start_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    expected = {"challenge_id": str(uuid4())}
    captured_kwargs: dict[str, object] = {}

    async def _fake_create_best_of_three(session_arg, **kwargs):
        captured_kwargs["session"] = session_arg
        captured_kwargs.update(kwargs)
        return expected

    monkeypatch.setattr(
        friend_challenges_series,
        "create_series_start_friend_challenge",
        _fake_create_best_of_three,
    )

    result = await friend_challenges_series.create_friend_challenge_best_of_three(
        session,
        initiator_user_id=101,
        challenge_id=SERIES_A_ID,
        now_utc=NOW_UTC,
        best_of=5,
    )

    assert result is expected
    assert captured_kwargs == {
        "session": session,
        "initiator_user_id": 101,
        "challenge_id": SERIES_A_ID,
        "now_utc": NOW_UTC,
        "best_of": 5,
    }


@pytest.mark.asyncio
async def test_create_friend_challenge_series_next_game_delegates_to_next_game_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    expected = {"challenge_id": str(uuid4())}
    captured_kwargs: dict[str, object] = {}

    async def _fake_create_series_next_game(session_arg, **kwargs):
        captured_kwargs["session"] = session_arg
        captured_kwargs.update(kwargs)
        return expected

    monkeypatch.setattr(
        friend_challenges_series,
        "create_series_next_game_friend_challenge",
        _fake_create_series_next_game,
    )

    result = await friend_challenges_series.create_friend_challenge_series_next_game(
        session,
        initiator_user_id=202,
        challenge_id=SERIES_C_ID,
        now_utc=NOW_UTC,
    )

    assert result is expected
    assert captured_kwargs == {
        "session": session,
        "initiator_user_id": 202,
        "challenge_id": SERIES_C_ID,
        "now_utc": NOW_UTC,
    }
