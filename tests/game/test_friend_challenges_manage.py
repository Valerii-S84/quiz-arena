from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_CANCELED, DUEL_STATUS_EXPIRED
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.service import friend_challenges_manage

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)


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
        _async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await func(
            SimpleNamespace(),
            user_id=11,
            challenge_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func", "challenge", "user_id"),
    [
        (
            friend_challenges_manage.repost_friend_challenge_as_open,
            _challenge(creator_user_id=11),
            999,
        ),
        (
            friend_challenges_manage.cancel_friend_challenge_by_creator,
            _challenge(status="ACCEPTED", creator_user_id=11),
            11,
        ),
    ],
)
async def test_manage_friend_challenge_rejects_access_checks(
    monkeypatch: pytest.MonkeyPatch,
    func,
    challenge: SimpleNamespace,
    user_id: int,
) -> None:
    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await func(
            SimpleNamespace(),
            user_id=user_id,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_repost_friend_challenge_as_open_creates_repost_and_emits_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(status="ACTIVE", creator_user_id=11, opponent_user_id=None)
    repost = SimpleNamespace(challenge_id=uuid4(), total_rounds=challenge.total_rounds)
    expired_events: list[dict[str, object]] = []
    analytics_events: list[dict[str, object]] = []
    create_calls: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = DUEL_STATUS_EXPIRED
        return True

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    async def _fake_create_friend_challenge(*_args, **kwargs):
        create_calls.append(kwargs)
        return repost

    async def _fake_emit_analytics_event(*_args, **kwargs) -> None:
        analytics_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        _fake_expire,
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "create_friend_challenge",
        _fake_create_friend_challenge,
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )

    result = await friend_challenges_manage.repost_friend_challenge_as_open(
        SimpleNamespace(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result is repost
    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_manage.EVENT_SOURCE_BOT,
        }
    ]
    assert create_calls == [
        {
            "creator_user_id": 11,
            "mode_code": challenge.mode_code,
            "now_utc": NOW_UTC,
            "challenge_type": friend_challenges_manage.DUEL_TYPE_OPEN,
            "total_rounds": challenge.total_rounds,
        }
    ]
    assert analytics_events == [
        {
            "event_type": "duel_reposted_as_open",
            "source": friend_challenges_manage.EVENT_SOURCE_BOT,
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
async def test_repost_friend_challenge_as_open_rejects_non_expired_creator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(status="ACCEPTED", creator_user_id=11)

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_manage.repost_friend_challenge_as_open(
            SimpleNamespace(),
            user_id=11,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


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
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: snapshot if challenge_row is challenge else None,
    )

    result = await friend_challenges_manage.cancel_friend_challenge_by_creator(
        SimpleNamespace(),
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
            "source": friend_challenges_manage.EVENT_SOURCE_BOT,
            "happened_at": NOW_UTC,
            "user_id": 11,
            "payload": {
                "challenge_id": str(challenge.id),
                "format": challenge.total_rounds,
            },
        }
    ]


@pytest.mark.asyncio
async def test_cancel_friend_challenge_by_creator_emits_expired_event_before_access_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(status="ACTIVE", creator_user_id=11, opponent_user_id=None)
    expired_events: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = DUEL_STATUS_EXPIRED
        return True

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(friend_challenges_manage, "_expire_friend_challenge_if_due", _fake_expire)
    monkeypatch.setattr(
        friend_challenges_manage,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_manage.cancel_friend_challenge_by_creator(
            SimpleNamespace(),
            user_id=999,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )

    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_manage.EVENT_SOURCE_BOT,
        }
    ]


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
