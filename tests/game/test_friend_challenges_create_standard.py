from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from app.game.sessions.service import (
    friend_challenges_create_drafts,
    friend_challenges_create_limits,
    friend_challenges_create_standard,
)
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
CHALLENGE_ID = UUID("11111111-1111-1111-1111-111111111111")


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


@pytest.mark.asyncio
async def test_create_friend_challenge_creates_standard_duel_and_emits_events(
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
    challenge_row = SimpleNamespace(id=CHALLENGE_ID, mode_code="QUICK_MIX_A1A2", total_rounds=5)
    create_calls: list[dict[str, object]] = []
    analytics_calls: list[dict[str, Any]] = []
    captured_draft_kwargs: dict[str, object] = {}

    async def _fake_build_create_draft(*args, **kwargs):
        del args
        captured_draft_kwargs.update(kwargs)
        return draft

    async def _fake_create_row(session, **kwargs):
        del session
        create_calls.append(kwargs)
        return challenge_row

    async def _fake_emit_standard_events(session, **kwargs):
        del session
        analytics_calls.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_create_standard,
        "resolve_friend_challenge_create_request",
        _async_return(
            friend_challenges_create_limits.FriendChallengeCreateRequest(
                challenge_type="DIRECT",
                total_rounds=5,
            )
        ),
    )
    monkeypatch.setattr(
        friend_challenges_create_standard,
        "build_create_friend_challenge_draft",
        _fake_build_create_draft,
    )
    monkeypatch.setattr(
        friend_challenges_create_standard,
        "create_friend_challenge_from_draft",
        _fake_create_row,
    )
    monkeypatch.setattr(
        friend_challenges_create_standard,
        "emit_standard_duel_created_events",
        _fake_emit_standard_events,
    )
    monkeypatch.setattr(
        friend_challenges_create_standard,
        "_build_friend_challenge_snapshot",
        lambda challenge: {"challenge_id": challenge.id},
    )

    result = await friend_challenges_create_standard.create_friend_challenge(
        _Session(),
        creator_user_id=101,
        mode_code="QUICK_MIX_A1A2",
        now_utc=NOW_UTC,
    )

    assert result == {"challenge_id": CHALLENGE_ID}
    assert captured_draft_kwargs == {
        "creator_user_id": 101,
        "challenge_type": "DIRECT",
        "mode_code": "QUICK_MIX_A1A2",
        "total_rounds": 5,
        "now_utc": NOW_UTC,
    }
    assert create_calls == [
        {
            "draft": draft,
            "now_utc": NOW_UTC,
        }
    ]
    assert analytics_calls == [
        {
            "challenge": challenge_row,
            "happened_at": NOW_UTC,
            "source": friend_challenges_create_standard.EVENT_SOURCE_BOT,
            "creator_user_id": 101,
        }
    ]
