from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.game.sessions.service import (
    friend_challenges_create_seed_state,
    friend_challenges_create_standard_draft,
)
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
CHALLENGE_ID = UUID("11111111-1111-1111-1111-111111111111")


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_build_create_friend_challenge_draft_uses_seed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_calls: list[dict[str, object]] = []

    async def _fake_load_seed_state(*_args, **kwargs):
        load_calls.append(kwargs)
        return friend_challenges_create_seed_state.FriendChallengeCreateSeedState(
            challenge_id=CHALLENGE_ID,
            access_type="FREE",
            question_ids=["q-1", "q-2", "q-3"],
        )

    monkeypatch.setattr(
        friend_challenges_create_standard_draft,
        "load_friend_challenge_create_seed_state",
        _fake_load_seed_state,
    )

    draft = await friend_challenges_create_standard_draft.build_create_friend_challenge_draft(
        _Session(),
        creator_user_id=101,
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        total_rounds=3,
        now_utc=NOW_UTC,
    )

    assert draft == friend_challenges_create_standard_draft.FriendChallengeCreationDraft(
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
    assert load_calls == [
        {
            "creator_user_id": 101,
            "mode_code": "QUICK_MIX_A1A2",
            "total_rounds": 3,
            "now_utc": NOW_UTC,
        }
    ]
