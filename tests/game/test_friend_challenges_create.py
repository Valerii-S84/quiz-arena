from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.game.sessions.service import friend_challenges_create, friend_challenges_create_drafts
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
CHALLENGE_ID = UUID("11111111-1111-1111-1111-111111111111")
SERIES_ID = UUID("22222222-2222-2222-2222-222222222222")


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


def _context(*, challenge: SimpleNamespace, opponent_user_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        challenge=challenge,
        opponent_user_id=opponent_user_id,
    )


@pytest.mark.asyncio
async def test_create_friend_challenge_delegates_to_standard_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = {"challenge_id": str(CHALLENGE_ID)}
    session = _Session()
    captured_kwargs: dict[str, object] = {}

    async def _fake_create_standard_friend_challenge(session, **kwargs):
        captured_kwargs["session"] = session
        captured_kwargs.update(kwargs)
        return snapshot

    monkeypatch.setattr(
        friend_challenges_create,
        "create_standard_friend_challenge",
        _fake_create_standard_friend_challenge,
    )

    result = await friend_challenges_create.create_friend_challenge(
        session,
        creator_user_id=101,
        mode_code="QUICK_MIX_A1A2",
        now_utc=NOW_UTC,
    )

    assert result is snapshot
    assert captured_kwargs == {
        "session": session,
        "creator_user_id": 101,
        "mode_code": "QUICK_MIX_A1A2",
        "now_utc": NOW_UTC,
        "challenge_type": "DIRECT",
        "total_rounds": friend_challenges_create.FRIEND_CHALLENGE_TOTAL_ROUNDS,
    }


@pytest.mark.asyncio
async def test_create_friend_challenge_rematch_creates_duel_and_emits_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = SimpleNamespace(id=CHALLENGE_ID, mode_code="QUICK_MIX_A1A2", total_rounds=7)
    draft = friend_challenges_create_drafts.FriendChallengeCreationDraft(
        challenge_id=uuid4(),
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
    rematch_row = SimpleNamespace(id=draft.challenge_id)
    create_calls: list[dict[str, object]] = []
    analytics_calls: list[dict[str, Any]] = []
    captured_draft_kwargs: dict[str, object] = {}

    async def _fake_build_rematch_draft(*args, **kwargs):
        del args
        captured_draft_kwargs.update(kwargs)
        return draft

    async def _fake_create_row(session, **kwargs):
        del session
        create_calls.append(kwargs)
        return rematch_row

    async def _fake_emit_rematch_events(session, **kwargs):
        del session
        analytics_calls.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_create,
        "load_friend_challenge_rematch_context",
        _async_return(_context(challenge=challenge, opponent_user_id=101)),
    )
    monkeypatch.setattr(
        friend_challenges_create,
        "build_rematch_friend_challenge_draft",
        _fake_build_rematch_draft,
    )
    monkeypatch.setattr(
        friend_challenges_create,
        "create_friend_challenge_from_draft",
        _fake_create_row,
    )
    monkeypatch.setattr(
        friend_challenges_create,
        "emit_rematch_duel_created_events",
        _fake_emit_rematch_events,
    )
    monkeypatch.setattr(
        friend_challenges_create,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: {"challenge_id": challenge_row.id},
    )

    result = await friend_challenges_create.create_friend_challenge_rematch(
        _Session(),
        initiator_user_id=202,
        challenge_id=CHALLENGE_ID,
        now_utc=NOW_UTC,
    )

    assert result == {"challenge_id": draft.challenge_id}
    assert captured_draft_kwargs == {
        "challenge": challenge,
        "initiator_user_id": 202,
        "opponent_user_id": 101,
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
            "rematch": rematch_row,
            "source_challenge_id": CHALLENGE_ID,
            "opponent_user_id": 101,
            "happened_at": NOW_UTC,
            "source": friend_challenges_create.EVENT_SOURCE_BOT,
            "initiator_user_id": 202,
        }
    ]
