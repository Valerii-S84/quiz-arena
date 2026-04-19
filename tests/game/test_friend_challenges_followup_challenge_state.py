from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.service import friend_challenges_followup_challenge_state
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _challenge(
    *,
    status: str = "COMPLETED",
    creator_user_id: int = 101,
    opponent_user_id: int | None = 202,
) -> FriendChallenge:
    return build_friend_challenge(
        id=uuid4(),
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        status=status,
        expires_at=NOW_UTC + timedelta(minutes=15),
    )


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


@pytest.mark.asyncio
async def test_load_followup_friend_challenge_raises_when_challenge_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_followup_challenge_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_followup_challenge_state.load_followup_friend_challenge(
            _Session(),
            initiator_user_id=101,
            challenge_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("challenge", "initiator_user_id"),
    [
        (_challenge(status="ACCEPTED"), 101),
        (_challenge(status="COMPLETED"), 999),
    ],
    ids=["active_status_rejected", "outsider_rejected"],
)
async def test_load_followup_friend_challenge_rejects_invalid_access(
    monkeypatch: pytest.MonkeyPatch,
    challenge: FriendChallenge,
    initiator_user_id: int,
) -> None:
    monkeypatch.setattr(
        friend_challenges_followup_challenge_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_followup_challenge_state,
        "_expire_friend_challenge_if_due",
        lambda **_: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_followup_challenge_state.load_followup_friend_challenge(
            _Session(),
            initiator_user_id=initiator_user_id,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_load_followup_friend_challenge_emits_expired_event_and_returns_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    expired_events: list[dict[str, object]] = []

    async def _fake_emit_expired_event(session, **kwargs):
        del session
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_followup_challenge_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_followup_challenge_state,
        "_expire_friend_challenge_if_due",
        lambda **_: True,
    )
    monkeypatch.setattr(
        friend_challenges_followup_challenge_state,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )

    result = await friend_challenges_followup_challenge_state.load_followup_friend_challenge(
        _Session(),
        initiator_user_id=101,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result is challenge
    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_followup_challenge_state.EVENT_SOURCE_BOT,
        }
    ]
