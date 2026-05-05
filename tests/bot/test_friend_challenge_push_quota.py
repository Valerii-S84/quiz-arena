from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import friend_challenge_push_quota
from app.game.sessions.service.constants import DUEL_MAX_PUSH_PER_USER
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
CHALLENGE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class _SessionLocal:
    def begin(self):
        return AsyncBeginContext(object())


@pytest.mark.asyncio
async def test_reserve_duel_push_slot_rejects_duplicate_push_after_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = SimpleNamespace(
        creator_user_id=11,
        opponent_user_id=22,
        creator_push_count=DUEL_MAX_PUSH_PER_USER,
        opponent_push_count=0,
        updated_at=None,
    )
    monkeypatch.setattr(
        friend_challenge_push_quota.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )

    reserved = await friend_challenge_push_quota.reserve_duel_push_slot(
        session_local=_SessionLocal(),
        challenge_id=CHALLENGE_ID,
        target_user_id=11,
        now_utc=NOW_UTC,
    )

    assert reserved is False
    assert challenge.creator_push_count == DUEL_MAX_PUSH_PER_USER
    assert challenge.updated_at is None


@pytest.mark.asyncio
async def test_reserve_duel_push_slot_rejects_random_nonparticipant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = SimpleNamespace(
        creator_user_id=11,
        opponent_user_id=22,
        creator_push_count=0,
        opponent_push_count=0,
        updated_at=None,
    )
    monkeypatch.setattr(
        friend_challenge_push_quota.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )

    reserved = await friend_challenge_push_quota.reserve_duel_push_slot(
        session_local=_SessionLocal(),
        challenge_id=CHALLENGE_ID,
        target_user_id=33,
        now_utc=NOW_UTC,
    )

    assert reserved is False
    assert challenge.creator_push_count == 0
    assert challenge.opponent_push_count == 0
    assert challenge.updated_at is None


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
