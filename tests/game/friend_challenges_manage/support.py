from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_BASELINE,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
)
from app.game.friend_challenges.constants import DUEL_STATUS_EXPIRED, DUEL_TYPE_DIRECT
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)


class SessionStub(AsyncSessionStub):
    async def flush(self, objects: Sequence[Any] | None = None) -> None:
        del objects


def challenge(
    *,
    status: str = DUEL_STATUS_EXPIRED,
    creator_user_id: int = 11,
    opponent_user_id: int | None = 22,
    challenge_type: str = DUEL_TYPE_DIRECT,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        challenge_type=challenge_type,
        status=status,
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        question_ids=[f"duel-q-{index}" for index in range(1, 8)],
        tournament_match_id=None,
        total_rounds=7,
        creator_score=6,
        creator_answered_round=7,
        creator_finished_at=NOW_UTC,
        completed_at=None,
        updated_at=None,
    )


def async_return(value):
    async def inner(*_args, **_kwargs):
        return value

    return inner


def arena_duel_from_friend(*, challenge_id, status: str = ARENA_DUEL_STATUS_ACTIVE) -> ArenaDuel:
    return ArenaDuel(
        id=uuid4(),
        creator_user_id=11,
        baseline_attempt_id=None,
        question_ids=[f"duel-q-{index}" for index in range(1, 8)],
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        status=status,
        expires_at=NOW_UTC.replace(hour=13),
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
        source_friend_challenge_id=challenge_id,
    )


def arena_baseline_attempt(*, duel_id) -> ArenaAttempt:
    return ArenaAttempt(
        id=uuid4(),
        arena_duel_id=duel_id,
        user_id=11,
        role=ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
        access_type="FREE",
        score=6,
        time_ms=48_000,
        result=ARENA_ATTEMPT_RESULT_BASELINE,
        completed_at=NOW_UTC,
        created_at=NOW_UTC,
    )
