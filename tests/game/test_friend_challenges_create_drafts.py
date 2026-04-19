from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.game.sessions.service import friend_challenges_create_drafts
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
CHALLENGE_ID = UUID("11111111-1111-1111-1111-111111111111")


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_build_create_friend_challenge_draft_delegates_to_standard_draft_builder(
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
async def test_build_rematch_friend_challenge_draft_delegates_to_rematch_draft_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    challenge = build_friend_challenge(mode_code="QUICK_MIX_A1A2", total_rounds=7)
    delegated_draft = friend_challenges_create_drafts.FriendChallengeCreationDraft(
        challenge_id=CHALLENGE_ID,
        creator_user_id=202,
        opponent_user_id=101,
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        access_type="PAID_TICKET",
        total_rounds=7,
        question_ids=["r-1", "r-2"],
        status="ACCEPTED",
        series_id=None,
        series_game_number=1,
        series_best_of=1,
    )
    captured_kwargs: dict[str, object] = {}

    async def _fake_build_rematch_draft(session_arg, **kwargs):
        captured_kwargs["session"] = session_arg
        captured_kwargs.update(kwargs)
        return delegated_draft

    monkeypatch.setattr(
        friend_challenges_create_drafts,
        "build_rematch_friend_challenge_draft_impl",
        _fake_build_rematch_draft,
    )

    draft = await friend_challenges_create_drafts.build_rematch_friend_challenge_draft(
        session,
        challenge=challenge,
        initiator_user_id=202,
        opponent_user_id=101,
        now_utc=NOW_UTC,
    )

    assert draft is delegated_draft
    assert captured_kwargs == {
        "session": session,
        "challenge": challenge,
        "initiator_user_id": 202,
        "opponent_user_id": 101,
        "now_utc": NOW_UTC,
    }
