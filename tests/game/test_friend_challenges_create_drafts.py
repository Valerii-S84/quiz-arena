from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.service import (
    friend_challenges_create_drafts,
    friend_challenges_create_rematch_series,
    friend_challenges_create_seed_state,
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


@pytest.mark.asyncio
async def test_build_create_friend_challenge_draft_uses_seed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    delegated_draft = friend_challenges_create_drafts.FriendChallengeCreationDraft(
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
    captured_kwargs: dict[str, object] = {}

    async def _fake_build_standard_draft(session_arg, **kwargs):
        captured_kwargs["session"] = session_arg
        captured_kwargs.update(kwargs)
        return delegated_draft

    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "build_standard_friend_challenge_draft",
        _fake_build_standard_draft,
    )

    draft = await friend_challenges_create_drafts.build_create_friend_challenge_draft(
        session,
        creator_user_id=101,
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        total_rounds=3,
        now_utc=NOW_UTC,
    )

    assert draft is delegated_draft
    assert captured_kwargs == {
        "session": session,
        "creator_user_id": 101,
        "challenge_type": "DIRECT",
        "mode_code": "QUICK_MIX_A1A2",
        "total_rounds": 3,
        "now_utc": NOW_UTC,
    }


@pytest.mark.asyncio
async def test_build_rematch_friend_challenge_draft_uses_series_state_and_seed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(total_rounds=5)
    load_calls: list[dict[str, object]] = []

    async def _fake_resolve_series_state(*_args, **_kwargs):
        return friend_challenges_create_rematch_series.FriendChallengeRematchSeriesState(
            series_id=SERIES_ID,
            series_game_number=2,
            series_best_of=3,
        )

    async def _fake_load_seed_state(*_args, **kwargs):
        load_calls.append(kwargs)
        return friend_challenges_create_seed_state.FriendChallengeCreateSeedState(
            challenge_id=CHALLENGE_ID,
            access_type="PAID_TICKET",
            question_ids=["r-1", "r-2", "r-3"],
        )

    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "resolve_friend_challenge_rematch_series_state",
        _fake_resolve_series_state,
    )
    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "load_friend_challenge_create_seed_state",
        _fake_load_seed_state,
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
    assert load_calls == [
        {
            "creator_user_id": 202,
            "mode_code": challenge.mode_code,
            "total_rounds": challenge.total_rounds,
            "now_utc": NOW_UTC,
        }
    ]


@pytest.mark.asyncio
async def test_build_rematch_friend_challenge_draft_resets_series_when_helper_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(series_id=SERIES_ID, series_best_of=3)

    async def _fake_resolve_series_state(*_args, **_kwargs):
        return friend_challenges_create_rematch_series.FriendChallengeRematchSeriesState(
            series_id=None,
            series_game_number=1,
            series_best_of=1,
        )

    async def _fake_load_seed_state(*_args, **_kwargs):
        return friend_challenges_create_seed_state.FriendChallengeCreateSeedState(
            challenge_id=CHALLENGE_ID,
            access_type="FREE",
            question_ids=["r-1"],
        )

    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "resolve_friend_challenge_rematch_series_state",
        _fake_resolve_series_state,
    )
    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "load_friend_challenge_create_seed_state",
        _fake_load_seed_state,
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
