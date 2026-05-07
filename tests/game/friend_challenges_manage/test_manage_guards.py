from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.service import friend_challenges_manage

from .support import NOW_UTC, SessionStub, async_return, challenge


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "func",
    [
        friend_challenges_manage.repost_friend_challenge_as_open,
        friend_challenges_manage.cancel_friend_challenge_by_creator,
    ],
)
async def test_manage_friend_challenge_raises_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
    func,
) -> None:
    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await func(SessionStub(), user_id=11, challenge_id=uuid4(), now_utc=NOW_UTC)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func", "current_challenge", "user_id"),
    [
        (
            friend_challenges_manage.repost_friend_challenge_as_open,
            challenge(creator_user_id=11),
            999,
        ),
        (
            friend_challenges_manage.cancel_friend_challenge_by_creator,
            challenge(status="ACCEPTED", creator_user_id=11),
            11,
        ),
    ],
)
async def test_manage_friend_challenge_rejects_access_checks(
    monkeypatch: pytest.MonkeyPatch,
    func,
    current_challenge: SimpleNamespace,
    user_id: int,
) -> None:
    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(current_challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await func(
            SessionStub(),
            user_id=user_id,
            challenge_id=current_challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_repost_friend_challenge_as_open_rejects_non_expired_creator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_challenge = challenge(status="ACCEPTED", creator_user_id=11)

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(current_challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_manage.repost_friend_challenge_as_open(
            SessionStub(),
            user_id=11,
            challenge_id=current_challenge.id,
            now_utc=NOW_UTC,
        )
