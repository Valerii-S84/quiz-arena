from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.game.friend_challenges.constants import DUEL_STATUS_PENDING, DUEL_TYPE_DIRECT
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_access import (
    _resolve_friend_challenge_access_type as resolve_friend_challenge_access_type,
)
from .friend_challenges_records import (
    _build_friend_challenge_snapshot as build_friend_challenge_snapshot,
)
from .friend_challenges_records import _create_friend_challenge_row as create_friend_challenge_row


async def _resolve_friend_challenge_access_type(
    session: AsyncSession,
    *,
    creator_user_id: int,
    now_utc: datetime,
) -> str:
    return await resolve_friend_challenge_access_type(
        session,
        creator_user_id=creator_user_id,
        now_utc=now_utc,
    )


async def _create_friend_challenge_row(
    session: AsyncSession,
    *,
    challenge_id: UUID | None = None,
    creator_user_id: int,
    opponent_user_id: int | None,
    challenge_type: str = DUEL_TYPE_DIRECT,
    mode_code: str,
    access_type: str,
    total_rounds: int,
    now_utc: datetime,
    question_ids: list[str] | None = None,
    series_id: UUID | None = None,
    series_game_number: int = 1,
    series_best_of: int = 1,
    status: str = DUEL_STATUS_PENDING,
) -> FriendChallenge:
    return await create_friend_challenge_row(
        session,
        challenge_id=challenge_id,
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        challenge_type=challenge_type,
        mode_code=mode_code,
        access_type=access_type,
        total_rounds=total_rounds,
        now_utc=now_utc,
        question_ids=question_ids,
        series_id=series_id,
        series_game_number=series_game_number,
        series_best_of=series_best_of,
        status=status,
    )


def _build_friend_challenge_snapshot(challenge: FriendChallenge) -> FriendChallengeSnapshot:
    return build_friend_challenge_snapshot(challenge)
