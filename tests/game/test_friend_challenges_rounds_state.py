from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.errors import FriendChallengeCompletedError, FriendChallengeFullError
from app.game.sessions.service import (
    friend_challenges_round_challenge_state,
    friend_challenges_rounds_state,
)
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _challenge(**overrides: object) -> FriendChallenge:
    payload: dict[str, object] = {
        "mode_code": "QUICK_MIX_A1A2",
        "total_rounds": 7,
    }
    payload.update(overrides)
    return build_friend_challenge(**payload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "is_creator", "answered_round", "expected_next_round"),
    [
        (10, True, 1, 2),
        (20, False, 3, 4),
    ],
    ids=["creator_context", "opponent_context"],
)
async def test_load_friend_challenge_round_context_delegates_and_builds_context(
    monkeypatch: pytest.MonkeyPatch,
    user_id: int,
    is_creator: bool,
    answered_round: int,
    expected_next_round: int,
) -> None:
    session = _Session()
    challenge = _challenge(
        creator_user_id=10,
        opponent_user_id=20,
        creator_answered_round=answered_round if is_creator else 0,
        opponent_answered_round=0 if is_creator else answered_round,
    )
    challenge_state = friend_challenges_round_challenge_state.FriendChallengeRoundChallengeState(
        challenge=challenge,
        has_opponent=True,
        is_creator=is_creator,
    )
    captured_kwargs: dict[str, object] = {}

    async def _fake_load_round_friend_challenge(session, **kwargs):
        captured_kwargs["session"] = session
        captured_kwargs.update(kwargs)
        return challenge_state

    monkeypatch.setattr(
        friend_challenges_rounds_state,
        "load_round_friend_challenge",
        _fake_load_round_friend_challenge,
    )

    context = await friend_challenges_rounds_state.load_friend_challenge_round_context(
        session,
        challenge_id=challenge.id,
        user_id=user_id,
        now_utc=NOW_UTC,
    )

    assert context == friend_challenges_rounds_state._FriendChallengeRoundContext(
        challenge=challenge,
        has_opponent=True,
        is_creator=is_creator,
        next_round=expected_next_round,
    )
    assert captured_kwargs == {
        "session": session,
        "challenge_id": challenge.id,
        "user_id": user_id,
        "now_utc": NOW_UTC,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("has_opponent", "expected_error"),
    [
        (False, FriendChallengeFullError),
        (True, FriendChallengeCompletedError),
    ],
    ids=["full_without_opponent", "completed_with_opponent"],
)
async def test_load_friend_challenge_round_context_rejects_non_playable_context(
    monkeypatch: pytest.MonkeyPatch,
    has_opponent: bool,
    expected_error: type[Exception],
) -> None:
    challenge = _challenge(opponent_user_id=20 if has_opponent else None)
    challenge_state = friend_challenges_round_challenge_state.FriendChallengeRoundChallengeState(
        challenge=challenge,
        has_opponent=has_opponent,
        is_creator=True,
    )

    async def _fake_load_round_friend_challenge(*_args, **_kwargs):
        return challenge_state

    monkeypatch.setattr(
        friend_challenges_rounds_state,
        "load_round_friend_challenge",
        _fake_load_round_friend_challenge,
    )
    monkeypatch.setattr(
        friend_challenges_rounds_state,
        "is_round_playable",
        lambda *_args, **_kwargs: False,
    )

    with pytest.raises(expected_error):
        await friend_challenges_rounds_state.load_friend_challenge_round_context(
            _Session(),
            challenge_id=challenge.id,
            user_id=10,
            now_utc=NOW_UTC,
        )
