from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.errors import FriendChallengeAccessError
from app.game.sessions.service import friend_challenges_series_drafts
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
SERIES_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class _Session(AsyncSessionStub):
    pass


def _challenge(
    *,
    status: str = "COMPLETED",
    creator_user_id: int = 101,
    opponent_user_id: int | None = 202,
    series_id: UUID | None = None,
    series_game_number: int = 1,
    series_best_of: int = 1,
    winner_user_id: int | None = None,
) -> FriendChallenge:
    return build_friend_challenge(
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


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


@pytest.mark.asyncio
async def test_build_series_start_friend_challenge_draft_normalizes_best_of(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    fixed_series_id = uuid4()
    monkeypatch.setattr(friend_challenges_series_drafts, "uuid4", lambda: fixed_series_id)
    monkeypatch.setattr(
        friend_challenges_series_drafts,
        "_resolve_friend_challenge_access_type",
        _async_return("FREE"),
    )

    draft = await friend_challenges_series_drafts.build_series_start_friend_challenge_draft(
        _Session(),
        challenge=challenge,
        initiator_user_id=101,
        opponent_user_id=202,
        now_utc=NOW_UTC,
        best_of=0,
    )

    assert draft == friend_challenges_series_drafts.FriendChallengeSeriesDraft(
        creator_user_id=101,
        opponent_user_id=202,
        challenge_type="DIRECT",
        mode_code=challenge.mode_code,
        access_type="FREE",
        total_rounds=challenge.total_rounds,
        series_id=fixed_series_id,
        series_game_number=1,
        series_best_of=1,
        status="ACCEPTED",
    )


@pytest.mark.asyncio
async def test_build_series_next_game_friend_challenge_draft_uses_next_game_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(
        creator_user_id=101,
        opponent_user_id=202,
        series_id=SERIES_A_ID,
        series_game_number=1,
        series_best_of=3,
        winner_user_id=101,
    )
    monkeypatch.setattr(
        friend_challenges_series_drafts.FriendChallengesRepo,
        "list_by_series_id_for_update",
        _async_return([challenge]),
    )
    monkeypatch.setattr(
        friend_challenges_series_drafts,
        "_resolve_friend_challenge_access_type",
        _async_return("PAID_TICKET"),
    )

    draft = await friend_challenges_series_drafts.build_series_next_game_friend_challenge_draft(
        _Session(),
        challenge=challenge,
        initiator_user_id=202,
        opponent_user_id=101,
        now_utc=NOW_UTC,
    )

    assert draft == friend_challenges_series_drafts.FriendChallengeSeriesDraft(
        creator_user_id=202,
        opponent_user_id=101,
        challenge_type="DIRECT",
        mode_code=challenge.mode_code,
        access_type="PAID_TICKET",
        total_rounds=challenge.total_rounds,
        series_id=SERIES_A_ID,
        series_game_number=2,
        series_best_of=3,
        status="ACCEPTED",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("challenge", "series_challenges"),
    [
        (_challenge(series_id=None, series_best_of=1), []),
        (
            _challenge(series_id=SERIES_A_ID, series_game_number=2, series_best_of=3),
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
        ),
    ],
    ids=["missing_series_metadata", "winner_already_decided"],
)
async def test_build_series_next_game_friend_challenge_draft_rejects_ineligible_series(
    monkeypatch: pytest.MonkeyPatch,
    challenge: FriendChallenge,
    series_challenges: list[FriendChallenge],
) -> None:
    monkeypatch.setattr(
        friend_challenges_series_drafts.FriendChallengesRepo,
        "list_by_series_id_for_update",
        _async_return(series_challenges),
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_series_drafts.build_series_next_game_friend_challenge_draft(
            _Session(),
            challenge=challenge,
            initiator_user_id=101,
            opponent_user_id=202,
            now_utc=NOW_UTC,
        )
