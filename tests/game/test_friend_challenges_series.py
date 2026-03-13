from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.service import friend_challenges_series

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
SERIES_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SERIES_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SERIES_C_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _challenge(
    *,
    status: str = "COMPLETED",
    creator_user_id: int = 101,
    opponent_user_id: int | None = 202,
    series_id: UUID | None = None,
    series_game_number: int = 1,
    series_best_of: int = 1,
    winner_user_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        mode_code="QUICK_MIX_A1A2",
        total_rounds=7,
        status=status,
        series_id=series_id,
        series_game_number=series_game_number,
        series_best_of=series_best_of,
        winner_user_id=winner_user_id,
        expires_at=NOW_UTC + timedelta(minutes=15),
    )


def _duel(
    *,
    duel_id: UUID | None = None,
    access_type: str = "FREE",
    series_id: UUID | None = None,
    series_game_number: int = 1,
    series_best_of: int = 3,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=duel_id or uuid4(),
        mode_code="QUICK_MIX_A1A2",
        access_type=access_type,
        total_rounds=7,
        series_id=series_id,
        series_game_number=series_game_number,
        series_best_of=series_best_of,
        expires_at=NOW_UTC + timedelta(minutes=15),
    )


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


@pytest.mark.asyncio
async def test_create_friend_challenge_best_of_three_raises_when_challenge_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_series.FriendChallengesRepo, "get_by_id_for_update", _async_return(None)
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_series.create_friend_challenge_best_of_three(
            SimpleNamespace(), initiator_user_id=101, challenge_id=uuid4(), now_utc=NOW_UTC
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "initiator_user_id"),
    [("ACCEPTED", 101), ("COMPLETED", 999)],
    ids=["active_status_rejected", "outsider_rejected"],
)
async def test_create_friend_challenge_best_of_three_rejects_invalid_access(
    monkeypatch: pytest.MonkeyPatch, status: str, initiator_user_id: int
) -> None:
    monkeypatch.setattr(
        friend_challenges_series.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(_challenge(status=status)),
    )
    monkeypatch.setattr(
        friend_challenges_series, "_expire_friend_challenge_if_due", lambda **_: False
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_series.create_friend_challenge_best_of_three(
            SimpleNamespace(),
            initiator_user_id=initiator_user_id,
            challenge_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_create_friend_challenge_best_of_three_creates_series_duel_and_emits_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    fixed_series_id = uuid4()
    duel = _duel(series_id=fixed_series_id, series_best_of=5)
    expired_events: list[dict[str, object]] = []
    analytics_events: list[dict[str, object]] = []
    create_calls: list[dict[str, object]] = []

    async def _fake_create_row(session, **kwargs):
        del session
        create_calls.append(kwargs)
        return duel

    async def _fake_emit_expired_event(session, **kwargs):
        del session
        expired_events.append(kwargs)

    async def _fake_emit_analytics_event(session, **kwargs):
        del session
        analytics_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_series.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(friend_challenges_series, "uuid4", lambda: fixed_series_id)
    monkeypatch.setattr(
        friend_challenges_series, "_expire_friend_challenge_if_due", lambda **_: True
    )
    monkeypatch.setattr(
        friend_challenges_series, "_emit_friend_challenge_expired_event", _fake_emit_expired_event
    )
    monkeypatch.setattr(
        friend_challenges_series, "_resolve_friend_challenge_access_type", _async_return("FREE")
    )
    monkeypatch.setattr(friend_challenges_series, "_create_friend_challenge_row", _fake_create_row)
    monkeypatch.setattr(
        friend_challenges_series, "emit_analytics_event", _fake_emit_analytics_event
    )
    monkeypatch.setattr(
        friend_challenges_series,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: {"challenge_id": challenge_row.id},
    )

    result = await friend_challenges_series.create_friend_challenge_best_of_three(
        SimpleNamespace(),
        initiator_user_id=101,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
        best_of=5,
    )

    assert result == {"challenge_id": duel.id}
    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_series.EVENT_SOURCE_BOT,
        }
    ]
    assert create_calls == [
        {
            "creator_user_id": 101,
            "opponent_user_id": 202,
            "challenge_type": "DIRECT",
            "mode_code": challenge.mode_code,
            "access_type": "FREE",
            "total_rounds": challenge.total_rounds,
            "now_utc": NOW_UTC,
            "series_id": fixed_series_id,
            "series_game_number": 1,
            "series_best_of": 5,
            "status": DUEL_STATUS_ACCEPTED,
        }
    ]
    assert [event["event_type"] for event in analytics_events] == [
        "friend_challenge_created",
        "friend_challenge_series_started",
    ]
    assert analytics_events[0]["payload"]["entrypoint"] == "best_of_series"
    assert analytics_events[1]["payload"]["series_id"] == str(fixed_series_id)


@pytest.mark.asyncio
async def test_create_friend_challenge_series_next_game_rejects_without_series_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(series_id=None, series_best_of=1)

    async def _unexpected_list_series(*args, **kwargs):
        del args, kwargs
        pytest.fail("series lookup should not happen without valid series metadata")

    monkeypatch.setattr(
        friend_challenges_series.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_series, "_expire_friend_challenge_if_due", lambda **_: False
    )
    monkeypatch.setattr(
        friend_challenges_series.FriendChallengesRepo,
        "list_by_series_id_for_update",
        _unexpected_list_series,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_series.create_friend_challenge_series_next_game(
            SimpleNamespace(),
            initiator_user_id=101,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("series_challenges", "challenge"),
    [
        (
            [
                _challenge(
                    series_id=SERIES_A_ID,
                    series_game_number=1,
                    series_best_of=3,
                    winner_user_id=101,
                ),
                _challenge(
                    series_id=SERIES_A_ID,
                    series_game_number=2,
                    series_best_of=3,
                    winner_user_id=101,
                ),
            ],
            _challenge(series_id=SERIES_A_ID, series_game_number=2, series_best_of=3),
        ),
        (
            [
                _challenge(
                    series_id=SERIES_B_ID,
                    series_game_number=1,
                    series_best_of=3,
                    winner_user_id=101,
                ),
                _challenge(
                    status="WALKOVER",
                    series_id=SERIES_B_ID,
                    series_game_number=3,
                    series_best_of=3,
                    winner_user_id=202,
                ),
            ],
            _challenge(series_id=SERIES_B_ID, series_game_number=2, series_best_of=3),
        ),
    ],
    ids=["winner_already_decided", "max_game_number_reached"],
)
async def test_create_friend_challenge_series_next_game_rejects_finished_series(
    monkeypatch: pytest.MonkeyPatch,
    series_challenges: list[SimpleNamespace],
    challenge: SimpleNamespace,
) -> None:
    monkeypatch.setattr(
        friend_challenges_series.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_series, "_expire_friend_challenge_if_due", lambda **_: False
    )
    monkeypatch.setattr(
        friend_challenges_series.FriendChallengesRepo,
        "list_by_series_id_for_update",
        _async_return(series_challenges),
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_series.create_friend_challenge_series_next_game(
            SimpleNamespace(),
            initiator_user_id=101,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_create_friend_challenge_series_next_game_creates_followup_duel_and_emits_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(
        creator_user_id=101,
        opponent_user_id=202,
        series_id=SERIES_C_ID,
        series_game_number=1,
        series_best_of=3,
        winner_user_id=101,
    )
    duel = _duel(access_type="PAID_TICKET", series_id=SERIES_C_ID, series_game_number=2)
    analytics_events: list[dict[str, object]] = []
    create_calls: list[dict[str, object]] = []

    async def _fake_create_row(session, **kwargs):
        del session
        create_calls.append(kwargs)
        return duel

    async def _fake_emit_analytics_event(session, **kwargs):
        del session
        analytics_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_series.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_series, "_expire_friend_challenge_if_due", lambda **_: False
    )
    monkeypatch.setattr(
        friend_challenges_series.FriendChallengesRepo,
        "list_by_series_id_for_update",
        _async_return([challenge]),
    )
    monkeypatch.setattr(
        friend_challenges_series,
        "_resolve_friend_challenge_access_type",
        _async_return("PAID_TICKET"),
    )
    monkeypatch.setattr(friend_challenges_series, "_create_friend_challenge_row", _fake_create_row)
    monkeypatch.setattr(
        friend_challenges_series, "emit_analytics_event", _fake_emit_analytics_event
    )
    monkeypatch.setattr(
        friend_challenges_series,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: {"challenge_id": challenge_row.id},
    )

    result = await friend_challenges_series.create_friend_challenge_series_next_game(
        SimpleNamespace(),
        initiator_user_id=202,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == {"challenge_id": duel.id}
    assert create_calls == [
        {
            "creator_user_id": 202,
            "opponent_user_id": 101,
            "challenge_type": "DIRECT",
            "mode_code": challenge.mode_code,
            "access_type": "PAID_TICKET",
            "total_rounds": challenge.total_rounds,
            "now_utc": NOW_UTC,
            "series_id": SERIES_C_ID,
            "series_game_number": 2,
            "series_best_of": 3,
            "status": DUEL_STATUS_ACCEPTED,
        }
    ]
    assert [event["event_type"] for event in analytics_events] == [
        "friend_challenge_created",
        "friend_challenge_series_game_created",
    ]
    assert analytics_events[0]["payload"]["entrypoint"] == "best_of_series_next_game"
    assert analytics_events[1]["payload"]["opponent_user_id"] == 101
