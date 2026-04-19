from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.service import (
    friend_challenges_create_drafts,
    friend_challenges_create_rematch_series,
)
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
CHALLENGE_ID = UUID("11111111-1111-1111-1111-111111111111")
SERIES_ID = UUID("22222222-2222-2222-2222-222222222222")


class _Session(AsyncSessionStub):
    pass


def _challenge(**overrides: object) -> FriendChallenge:
    payload: dict[str, object] = {
        "id": uuid4(),
        "creator_user_id": 101,
        "opponent_user_id": 202,
        "mode_code": "QUICK_MIX_A1A2",
        "total_rounds": 7,
        "expires_at": NOW_UTC + timedelta(minutes=15),
    }
    payload.update(overrides)
    return build_friend_challenge(**payload)


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


@pytest.mark.asyncio
async def test_build_create_friend_challenge_draft_resolves_access_and_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(friend_challenges_create_drafts, "uuid4", lambda: CHALLENGE_ID)
    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "_resolve_friend_challenge_access_type",
        _async_return("FREE"),
    )
    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "select_duel_question_ids",
        _async_return(["q-1", "q-2", "q-3"]),
    )

    draft = await friend_challenges_create_drafts.build_create_friend_challenge_draft(
        _Session(),
        creator_user_id=101,
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        total_rounds=3,
        now_utc=NOW_UTC,
    )

    assert draft == friend_challenges_create_drafts.FriendChallengeCreationDraft(
        challenge_id=CHALLENGE_ID,
        creator_user_id=101,
        opponent_user_id=None,
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        total_rounds=3,
        question_ids=["q-1", "q-2", "q-3"],
        status="PENDING",
    )


@pytest.mark.asyncio
async def test_build_rematch_friend_challenge_draft_uses_series_state_access_and_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(total_rounds=5)
    monkeypatch.setattr(friend_challenges_create_drafts, "uuid4", lambda: CHALLENGE_ID)
    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "resolve_friend_challenge_rematch_series_state",
        _async_return(
            friend_challenges_create_rematch_series.FriendChallengeRematchSeriesState(
                series_id=SERIES_ID,
                series_game_number=2,
                series_best_of=3,
            )
        ),
    )
    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "_resolve_friend_challenge_access_type",
        _async_return("PAID_TICKET"),
    )
    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "select_duel_question_ids",
        _async_return(["r-1", "r-2", "r-3"]),
    )

    draft = await friend_challenges_create_drafts.build_rematch_friend_challenge_draft(
        _Session(),
        challenge=challenge,
        initiator_user_id=202,
        opponent_user_id=101,
        now_utc=NOW_UTC,
    )

    assert draft == friend_challenges_create_drafts.FriendChallengeCreationDraft(
        challenge_id=CHALLENGE_ID,
        creator_user_id=202,
        opponent_user_id=101,
        challenge_type="DIRECT",
        mode_code=challenge.mode_code,
        access_type="PAID_TICKET",
        total_rounds=challenge.total_rounds,
        question_ids=["r-1", "r-2", "r-3"],
        status="ACCEPTED",
        series_id=SERIES_ID,
        series_game_number=2,
        series_best_of=3,
    )


@pytest.mark.asyncio
async def test_build_rematch_friend_challenge_draft_resets_series_when_helper_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(series_id=SERIES_ID, series_best_of=3)
    monkeypatch.setattr(friend_challenges_create_drafts, "uuid4", lambda: CHALLENGE_ID)
    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "resolve_friend_challenge_rematch_series_state",
        _async_return(
            friend_challenges_create_rematch_series.FriendChallengeRematchSeriesState(
                series_id=None,
                series_game_number=1,
                series_best_of=1,
            )
        ),
    )
    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "_resolve_friend_challenge_access_type",
        _async_return("FREE"),
    )
    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "select_duel_question_ids",
        _async_return(["r-1"]),
    )

    draft = await friend_challenges_create_drafts.build_rematch_friend_challenge_draft(
        _Session(),
        challenge=challenge,
        initiator_user_id=202,
        opponent_user_id=101,
        now_utc=NOW_UTC,
    )

    assert draft.series_id is None
    assert draft.series_game_number == 1
    assert draft.series_best_of == 1
