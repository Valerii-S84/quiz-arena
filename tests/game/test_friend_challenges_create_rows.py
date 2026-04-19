from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.game.sessions.service import friend_challenges_create_drafts, friend_challenges_create_rows
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 3, 17, 12, 0, tzinfo=UTC)
CHALLENGE_ID = UUID("11111111-1111-1111-1111-111111111111")
SERIES_ID = UUID("22222222-2222-2222-2222-222222222222")


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_create_friend_challenge_from_draft_persists_standard_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = friend_challenges_create_drafts.FriendChallengeCreationDraft(
        challenge_id=CHALLENGE_ID,
        creator_user_id=101,
        opponent_user_id=None,
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        total_rounds=5,
        question_ids=["q-1", "q-2"],
        status="PENDING",
    )
    create_calls: list[dict[str, object]] = []
    created_row = SimpleNamespace(id=CHALLENGE_ID)

    async def _fake_create_friend_challenge_row(session, **kwargs):
        del session
        create_calls.append(kwargs)
        return created_row

    monkeypatch.setattr(
        friend_challenges_create_rows,
        "_create_friend_challenge_row",
        _fake_create_friend_challenge_row,
    )

    result = await friend_challenges_create_rows.create_friend_challenge_from_draft(
        _Session(),
        draft=draft,
        now_utc=NOW_UTC,
    )

    assert result is created_row
    assert create_calls == [
        {
            "challenge_id": CHALLENGE_ID,
            "creator_user_id": 101,
            "opponent_user_id": None,
            "challenge_type": "DIRECT",
            "mode_code": "QUICK_MIX_A1A2",
            "access_type": "FREE",
            "total_rounds": 5,
            "now_utc": NOW_UTC,
            "question_ids": ["q-1", "q-2"],
            "series_id": None,
            "series_game_number": 1,
            "series_best_of": 1,
            "status": "PENDING",
        }
    ]


@pytest.mark.asyncio
async def test_create_friend_challenge_from_draft_persists_rematch_series_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = friend_challenges_create_drafts.FriendChallengeCreationDraft(
        challenge_id=CHALLENGE_ID,
        creator_user_id=202,
        opponent_user_id=101,
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        access_type="PAID_TICKET",
        total_rounds=7,
        question_ids=["r-1", "r-2"],
        status="ACCEPTED",
        series_id=SERIES_ID,
        series_game_number=2,
        series_best_of=3,
    )
    create_calls: list[dict[str, object]] = []
    created_row = SimpleNamespace(id=CHALLENGE_ID)

    async def _fake_create_friend_challenge_row(session, **kwargs):
        del session
        create_calls.append(kwargs)
        return created_row

    monkeypatch.setattr(
        friend_challenges_create_rows,
        "_create_friend_challenge_row",
        _fake_create_friend_challenge_row,
    )

    result = await friend_challenges_create_rows.create_friend_challenge_from_draft(
        _Session(),
        draft=draft,
        now_utc=NOW_UTC,
    )

    assert result is created_row
    assert create_calls == [
        {
            "challenge_id": CHALLENGE_ID,
            "creator_user_id": 202,
            "opponent_user_id": 101,
            "challenge_type": "DIRECT",
            "mode_code": "QUICK_MIX_A1A2",
            "access_type": "PAID_TICKET",
            "total_rounds": 7,
            "now_utc": NOW_UTC,
            "question_ids": ["r-1", "r-2"],
            "series_id": SERIES_ID,
            "series_game_number": 2,
            "series_best_of": 3,
            "status": "ACCEPTED",
        }
    ]
