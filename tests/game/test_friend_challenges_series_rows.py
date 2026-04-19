from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.game.sessions.service import friend_challenges_series_drafts, friend_challenges_series_rows
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 3, 17, 12, 0, tzinfo=UTC)
SERIES_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_create_series_friend_challenge_from_draft_persists_series_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = friend_challenges_series_drafts.FriendChallengeSeriesDraft(
        creator_user_id=202,
        opponent_user_id=101,
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        access_type="PAID_TICKET",
        total_rounds=7,
        series_id=SERIES_ID,
        series_game_number=2,
        series_best_of=3,
        status="ACCEPTED",
    )
    create_calls: list[dict[str, object]] = []
    created_row = SimpleNamespace(id=SERIES_ID)

    async def _fake_create_friend_challenge_row(session, **kwargs):
        del session
        create_calls.append(kwargs)
        return created_row

    monkeypatch.setattr(
        friend_challenges_series_rows,
        "_create_friend_challenge_row",
        _fake_create_friend_challenge_row,
    )

    result = await friend_challenges_series_rows.create_series_friend_challenge_from_draft(
        _Session(),
        draft=draft,
        now_utc=NOW_UTC,
    )

    assert result is created_row
    assert create_calls == [
        {
            "creator_user_id": 202,
            "opponent_user_id": 101,
            "challenge_type": "DIRECT",
            "mode_code": "QUICK_MIX_A1A2",
            "access_type": "PAID_TICKET",
            "total_rounds": 7,
            "now_utc": NOW_UTC,
            "series_id": SERIES_ID,
            "series_game_number": 2,
            "series_best_of": 3,
            "status": "ACCEPTED",
        }
    ]
