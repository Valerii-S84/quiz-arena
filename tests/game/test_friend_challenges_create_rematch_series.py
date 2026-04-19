from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.service import friend_challenges_create_rematch_series
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
SERIES_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class _Session(AsyncSessionStub):
    pass


def _challenge(
    *,
    series_id: UUID | None = None,
    series_game_number: int = 1,
    series_best_of: int = 1,
    winner_user_id: int | None = None,
    status: str = "COMPLETED",
) -> FriendChallenge:
    return build_friend_challenge(
        id=uuid4(),
        creator_user_id=101,
        opponent_user_id=202,
        status=status,
        winner_user_id=winner_user_id,
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
@pytest.mark.parametrize(
    ("challenge", "expected_series_id"),
    [
        (_challenge(series_id=None, series_best_of=1), None),
        (_challenge(series_id=SERIES_ID, series_best_of=1), SERIES_ID),
    ],
    ids=["no_series_metadata", "best_of_one_keeps_existing_series_id"],
)
async def test_resolve_rematch_series_state_returns_default_state_without_active_series(
    monkeypatch: pytest.MonkeyPatch,
    challenge: FriendChallenge,
    expected_series_id: UUID | None,
) -> None:
    async def _unexpected_list_series(*args, **kwargs):
        del args, kwargs
        pytest.fail("series lookup should not run when no continued series is possible")

    monkeypatch.setattr(
        friend_challenges_create_rematch_series.FriendChallengesRepo,
        "list_by_series_id_for_update",
        _unexpected_list_series,
    )

    state = (
        await friend_challenges_create_rematch_series.resolve_friend_challenge_rematch_series_state(
            _Session(),
            challenge=challenge,
        )
    )

    assert state == friend_challenges_create_rematch_series.FriendChallengeRematchSeriesState(
        series_id=expected_series_id,
        series_game_number=1,
        series_best_of=1,
    )


@pytest.mark.asyncio
async def test_resolve_rematch_series_state_continues_series_when_matchup_is_still_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(series_id=SERIES_ID, series_game_number=1, series_best_of=3)
    monkeypatch.setattr(
        friend_challenges_create_rematch_series.FriendChallengesRepo,
        "list_by_series_id_for_update",
        _async_return([_challenge(series_id=SERIES_ID, series_game_number=1, series_best_of=3)]),
    )

    state = (
        await friend_challenges_create_rematch_series.resolve_friend_challenge_rematch_series_state(
            _Session(),
            challenge=challenge,
        )
    )

    assert state == friend_challenges_create_rematch_series.FriendChallengeRematchSeriesState(
        series_id=SERIES_ID,
        series_game_number=2,
        series_best_of=3,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "series_challenges",
    [
        [
            _challenge(
                series_id=SERIES_ID, series_game_number=1, series_best_of=3, winner_user_id=101
            ),
            _challenge(
                series_id=SERIES_ID, series_game_number=2, series_best_of=3, winner_user_id=101
            ),
        ],
        [
            _challenge(
                series_id=SERIES_ID, series_game_number=1, series_best_of=3, winner_user_id=101
            ),
            _challenge(
                series_id=SERIES_ID, series_game_number=3, series_best_of=3, winner_user_id=202
            ),
        ],
    ],
    ids=["winner_already_decided", "max_game_number_reached"],
)
async def test_resolve_rematch_series_state_resets_when_series_is_finished(
    monkeypatch: pytest.MonkeyPatch,
    series_challenges: list[FriendChallenge],
) -> None:
    challenge = _challenge(series_id=SERIES_ID, series_game_number=2, series_best_of=3)
    monkeypatch.setattr(
        friend_challenges_create_rematch_series.FriendChallengesRepo,
        "list_by_series_id_for_update",
        _async_return(series_challenges),
    )

    state = (
        await friend_challenges_create_rematch_series.resolve_friend_challenge_rematch_series_state(
            _Session(),
            challenge=challenge,
        )
    )

    assert state == friend_challenges_create_rematch_series.FriendChallengeRematchSeriesState(
        series_id=None,
        series_game_number=1,
        series_best_of=1,
    )
