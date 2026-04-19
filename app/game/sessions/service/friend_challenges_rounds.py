from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.sessions.types import FriendChallengeRoundStartResult

from .friend_challenges_records import _build_friend_challenge_snapshot
from .friend_challenges_rounds_start_state import (
    FriendChallengeRoundStartState,
    load_friend_challenge_round_start_state,
)


def _build_round_start_result(
    start_state: FriendChallengeRoundStartState,
) -> FriendChallengeRoundStartResult:
    return FriendChallengeRoundStartResult(
        snapshot=_build_friend_challenge_snapshot(start_state.context.challenge),
        start_result=start_state.start_result,
        waiting_for_opponent=start_state.waiting_for_opponent,
        already_answered_current_round=start_state.already_answered_current_round,
    )


async def start_friend_challenge_round(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    idempotency_key: str,
    now_utc: datetime,
) -> FriendChallengeRoundStartResult:
    start_state = await load_friend_challenge_round_start_state(
        session,
        user_id=user_id,
        challenge_id=challenge_id,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )
    return _build_round_start_result(start_state)
