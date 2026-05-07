from types import SimpleNamespace

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_EXPIRED
from app.game.sessions.service import friend_challenges_manage

from .support import NOW_UTC, SessionStub, async_return, challenge


@pytest.mark.asyncio
async def test_repost_friend_challenge_as_open_creates_repost_without_legacy_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_challenge = challenge(status="ACTIVE", creator_user_id=11, opponent_user_id=None)
    repost = SimpleNamespace(challenge_id=current_challenge.id, total_rounds=7)
    expired_events: list[dict[str, object]] = []
    analytics_events: list[dict[str, object]] = []
    create_calls: list[dict[str, object]] = []

    def fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = DUEL_STATUS_EXPIRED
        return True

    async def fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    async def fake_create_friend_challenge(*_args, **kwargs):
        create_calls.append(kwargs)
        return repost

    async def fake_emit_analytics_event(*_args, **kwargs) -> None:
        analytics_events.append(kwargs)

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
    monkeypatch.setattr(
        friend_challenges_manage,
        "create_friend_challenge",
        fake_create_friend_challenge,
    )
    monkeypatch.setattr(
        friend_challenges_manage,
        "emit_analytics_event",
        fake_emit_analytics_event,
    )

    result = await friend_challenges_manage.repost_friend_challenge_as_open(
        SessionStub(),
        user_id=11,
        challenge_id=current_challenge.id,
        now_utc=NOW_UTC,
    )

    assert result is repost
    assert expired_events == [
        {
            "challenge": current_challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_manage.EVENT_SOURCE_BOT,
        }
    ]
    assert create_calls == [
        {
            "creator_user_id": 11,
            "mode_code": current_challenge.mode_code,
            "now_utc": NOW_UTC,
            "challenge_type": friend_challenges_manage.DUEL_TYPE_OPEN,
            "total_rounds": current_challenge.total_rounds,
        }
    ]
    assert analytics_events == []
