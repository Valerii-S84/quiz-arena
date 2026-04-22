from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.game.sessions.service import friend_challenges_internal_factory
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
EXPLICIT_CHALLENGE_ID = UUID("33333333-3333-3333-3333-333333333333")


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_resolve_friend_challenge_access_type_delegates_to_access_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    captured_kwargs: dict[str, object] = {}

    async def _fake_resolve_friend_challenge_access_type(session, **kwargs):
        captured_kwargs["session"] = session
        captured_kwargs.update(kwargs)
        return "FREE"

    monkeypatch.setattr(
        friend_challenges_internal_factory,
        "resolve_friend_challenge_access_type",
        _fake_resolve_friend_challenge_access_type,
    )

    result = await friend_challenges_internal_factory._resolve_friend_challenge_access_type(
        session,
        creator_user_id=101,
        now_utc=NOW_UTC,
    )

    assert result == "FREE"
    assert captured_kwargs == {
        "session": session,
        "creator_user_id": 101,
        "now_utc": NOW_UTC,
    }


@pytest.mark.asyncio
async def test_create_friend_challenge_row_delegates_to_records_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_row = object()
    session = _Session()
    captured_kwargs: dict[str, object] = {}

    async def _fake_create_friend_challenge_row(session, **kwargs):
        captured_kwargs["session"] = session
        captured_kwargs.update(kwargs)
        return created_row

    monkeypatch.setattr(
        friend_challenges_internal_factory,
        "create_friend_challenge_row",
        _fake_create_friend_challenge_row,
    )

    result = await friend_challenges_internal_factory._create_friend_challenge_row(
        session,
        challenge_id=EXPLICIT_CHALLENGE_ID,
        creator_user_id=101,
        opponent_user_id=202,
        mode_code="QUICK_MIX_A1A2",
        access_type="PAID_TICKET",
        total_rounds=0,
        now_utc=NOW_UTC,
        series_game_number=0,
        series_best_of=0,
        status="ACCEPTED",
    )

    assert result is created_row
    assert captured_kwargs == {
        "session": session,
        "challenge_id": EXPLICIT_CHALLENGE_ID,
        "creator_user_id": 101,
        "opponent_user_id": 202,
        "challenge_type": "DIRECT",
        "mode_code": "QUICK_MIX_A1A2",
        "access_type": "PAID_TICKET",
        "total_rounds": 0,
        "now_utc": NOW_UTC,
        "question_ids": None,
        "series_id": None,
        "series_game_number": 0,
        "series_best_of": 0,
        "status": "ACCEPTED",
    }


def test_build_friend_challenge_snapshot_delegates_to_records_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(id=EXPLICIT_CHALLENGE_ID)
    snapshot = object()

    def _fake_build_friend_challenge_snapshot(challenge_row):
        assert challenge_row is challenge
        return snapshot

    monkeypatch.setattr(
        friend_challenges_internal_factory,
        "build_friend_challenge_snapshot",
        _fake_build_friend_challenge_snapshot,
    )

    result = friend_challenges_internal_factory._build_friend_challenge_snapshot(challenge)

    assert result is snapshot
