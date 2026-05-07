import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_CANCELED, DUEL_STATUS_EXPIRED
from app.game.sessions.errors import FriendChallengeAccessError
from app.game.sessions.service import friend_challenges_manage

from .support import NOW_UTC, SessionStub, async_return, challenge


@pytest.mark.asyncio
async def test_cancel_friend_challenge_by_creator_marks_canceled_and_returns_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_challenge = challenge()
    analytics_events: list[dict[str, object]] = []
    snapshot = {"challenge_id": str(current_challenge.id), "status": DUEL_STATUS_CANCELED}

    async def fake_emit_analytics_event(*_args, **kwargs) -> None:
        analytics_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(current_challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage, "_expire_friend_challenge_if_due", lambda **_kwargs: False
    )
    monkeypatch.setattr(friend_challenges_manage, "emit_analytics_event", fake_emit_analytics_event)
    monkeypatch.setattr(
        friend_challenges_manage,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: snapshot if challenge_row is current_challenge else None,
    )

    result = await friend_challenges_manage.cancel_friend_challenge_by_creator(
        SessionStub(),
        user_id=11,
        challenge_id=current_challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == snapshot
    assert current_challenge.status == DUEL_STATUS_CANCELED
    assert current_challenge.completed_at == NOW_UTC
    assert current_challenge.updated_at == NOW_UTC
    assert analytics_events == [
        {
            "event_type": "duel_canceled_by_creator",
            "source": friend_challenges_manage.EVENT_SOURCE_BOT,
            "happened_at": NOW_UTC,
            "user_id": 11,
            "payload": {
                "challenge_id": str(current_challenge.id),
                "format": current_challenge.total_rounds,
            },
        }
    ]


@pytest.mark.asyncio
async def test_cancel_friend_challenge_by_creator_allows_pending_unjoined_duel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_challenge = challenge(status="PENDING", creator_user_id=11, opponent_user_id=None)

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(current_challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage, "_expire_friend_challenge_if_due", lambda **_kwargs: False
    )
    monkeypatch.setattr(friend_challenges_manage, "emit_analytics_event", async_return(None))
    monkeypatch.setattr(
        friend_challenges_manage,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: challenge_row,
    )

    result = await friend_challenges_manage.cancel_friend_challenge_by_creator(
        SessionStub(),
        user_id=11,
        challenge_id=current_challenge.id,
        now_utc=NOW_UTC,
    )

    assert result is current_challenge
    assert current_challenge.status == DUEL_STATUS_CANCELED
    assert current_challenge.completed_at == NOW_UTC


@pytest.mark.asyncio
async def test_cancel_friend_challenge_by_creator_emits_expired_event_before_access_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_challenge = challenge(status="ACTIVE", creator_user_id=11, opponent_user_id=None)
    expired_events: list[dict[str, object]] = []

    def fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = DUEL_STATUS_EXPIRED
        return True

    async def fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(current_challenge),
    )
    monkeypatch.setattr(friend_challenges_manage, "_expire_friend_challenge_if_due", fake_expire)
    monkeypatch.setattr(
        friend_challenges_manage,
        "_emit_friend_challenge_expired_event",
        fake_emit_expired_event,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_manage.cancel_friend_challenge_by_creator(
            SessionStub(),
            user_id=999,
            challenge_id=current_challenge.id,
            now_utc=NOW_UTC,
        )

    assert expired_events == [
        {
            "challenge": current_challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_manage.EVENT_SOURCE_BOT,
        }
    ]
