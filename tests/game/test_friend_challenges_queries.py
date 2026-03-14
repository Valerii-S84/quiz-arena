from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.service import friend_challenges_queries

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)


def _challenge(
    *,
    status: str = "ACCEPTED",
    creator_user_id: int = 11,
    opponent_user_id: int | None = 22,
    series_id=None,
    series_game_number: int = 1,
    series_best_of: int = 1,
    winner_user_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        status=status,
        series_id=series_id,
        series_game_number=series_game_number,
        series_best_of=series_best_of,
        winner_user_id=winner_user_id,
        expires_at=NOW_UTC,
    )


@pytest.mark.asyncio
async def test_get_friend_challenge_snapshot_for_user_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_queries.get_friend_challenge_snapshot_for_user(
            SimpleNamespace(),
            user_id=11,
            challenge_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_get_friend_challenge_snapshot_for_user_rejects_outsider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()

    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_queries,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_queries.get_friend_challenge_snapshot_for_user(
            SimpleNamespace(),
            user_id=999,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_get_friend_challenge_snapshot_for_user_expires_and_returns_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(status="ACTIVE", opponent_user_id=None)
    expired_events: list[dict[str, object]] = []
    snapshot = {"challenge_id": str(challenge.id), "status": "EXPIRED"}

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = "EXPIRED"
        return True

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(friend_challenges_queries, "_expire_friend_challenge_if_due", _fake_expire)
    monkeypatch.setattr(
        friend_challenges_queries,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )
    monkeypatch.setattr(
        friend_challenges_queries,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: snapshot if challenge_row is challenge else None,
    )

    result = await friend_challenges_queries.get_friend_challenge_snapshot_for_user(
        SimpleNamespace(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == snapshot
    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_queries.EVENT_SOURCE_BOT,
        }
    ]


@pytest.mark.asyncio
async def test_get_friend_series_score_for_user_returns_default_for_non_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(series_id=None, series_best_of=1)

    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_queries,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    result = await friend_challenges_queries.get_friend_series_score_for_user(
        SimpleNamespace(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == (0, 0, 1, 1)


@pytest.mark.asyncio
async def test_get_friend_series_score_for_user_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_queries.get_friend_series_score_for_user(
            SimpleNamespace(),
            user_id=11,
            challenge_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_get_friend_series_score_for_user_swaps_perspective_for_opponent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series_id = uuid4()
    challenge = _challenge(
        creator_user_id=11,
        opponent_user_id=22,
        series_id=series_id,
        series_game_number=3,
        series_best_of=5,
    )
    series_challenges = [
        _challenge(
            status="COMPLETED",
            creator_user_id=11,
            opponent_user_id=22,
            series_id=series_id,
            winner_user_id=11,
        ),
        _challenge(
            status="WALKOVER",
            creator_user_id=11,
            opponent_user_id=22,
            series_id=series_id,
            winner_user_id=22,
        ),
        _challenge(
            status="ACCEPTED",
            creator_user_id=11,
            opponent_user_id=22,
            series_id=series_id,
            winner_user_id=22,
        ),
    ]

    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_queries,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "list_by_series_id_for_update",
        _async_return(series_challenges),
    )

    result = await friend_challenges_queries.get_friend_series_score_for_user(
        SimpleNamespace(),
        user_id=22,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == (1, 1, 3, 5)


@pytest.mark.asyncio
async def test_get_friend_series_score_for_user_emits_expired_event_before_access_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(
        status="ACTIVE", opponent_user_id=None, series_id=uuid4(), series_best_of=3
    )
    expired_events: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = "EXPIRED"
        return True

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(friend_challenges_queries, "_expire_friend_challenge_if_due", _fake_expire)
    monkeypatch.setattr(
        friend_challenges_queries,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_queries.get_friend_series_score_for_user(
            SimpleNamespace(),
            user_id=999,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )

    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_queries.EVENT_SOURCE_BOT,
        }
    ]


@pytest.mark.asyncio
async def test_get_friend_series_score_for_user_returns_creator_perspective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series_id = uuid4()
    challenge = _challenge(
        creator_user_id=11,
        opponent_user_id=22,
        series_id=series_id,
        series_game_number=2,
        series_best_of=3,
    )
    series_challenges = [
        _challenge(
            status="COMPLETED",
            creator_user_id=11,
            opponent_user_id=22,
            series_id=series_id,
            winner_user_id=11,
        ),
        _challenge(
            status="COMPLETED",
            creator_user_id=11,
            opponent_user_id=22,
            series_id=series_id,
            winner_user_id=22,
        ),
    ]

    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_queries,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "list_by_series_id_for_update",
        _async_return(series_challenges),
    )

    result = await friend_challenges_queries.get_friend_series_score_for_user(
        SimpleNamespace(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == (1, 1, 2, 3)


@pytest.mark.asyncio
async def test_list_friend_challenges_for_user_expires_rows_and_builds_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_open = _challenge(status="ACTIVE", opponent_user_id=None)
    active_direct = _challenge(status="ACTIVE", opponent_user_id=22)
    expired_events: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        if challenge is active_open:
            challenge.status = "EXPIRED"
            return True
        return False

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "list_recent_for_user",
        _async_return([active_open, active_direct]),
    )
    monkeypatch.setattr(friend_challenges_queries, "_expire_friend_challenge_if_due", _fake_expire)
    monkeypatch.setattr(
        friend_challenges_queries,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )
    monkeypatch.setattr(
        friend_challenges_queries,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: {
            "challenge_id": str(challenge_row.id),
            "status": challenge_row.status,
        },
    )

    result = await friend_challenges_queries.list_friend_challenges_for_user(
        SimpleNamespace(),
        user_id=11,
        now_utc=NOW_UTC,
        limit=5,
    )

    assert result == [
        {"challenge_id": str(active_open.id), "status": "EXPIRED"},
        {"challenge_id": str(active_direct.id), "status": "ACCEPTED"},
    ]
    assert expired_events == [
        {
            "challenge": active_open,
            "happened_at": NOW_UTC,
            "source": friend_challenges_queries.EVENT_SOURCE_BOT,
        }
    ]


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
