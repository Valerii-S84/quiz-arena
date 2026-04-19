from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.friend_challenges_repo import FriendChallengesRepo

from .friend_challenges_query_state import load_friend_challenge_for_user
from .friend_challenges_series_utils import _count_series_wins


async def get_friend_series_score_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> tuple[int, int, int, int]:
    challenge = await load_friend_challenge_for_user(
        session,
        user_id=user_id,
        challenge_id=challenge_id,
        now_utc=now_utc,
    )
    if challenge.series_id is None or challenge.series_best_of <= 1:
        return (0, 0, 1, 1)

    series_challenges = await FriendChallengesRepo.list_by_series_id_for_update(
        session,
        series_id=challenge.series_id,
    )
    creator_wins, opponent_wins = _count_series_wins(
        series_challenges=series_challenges,
        creator_user_id=challenge.creator_user_id,
        opponent_user_id=challenge.opponent_user_id,
    )
    if user_id == challenge.creator_user_id:
        return (
            creator_wins,
            opponent_wins,
            challenge.series_game_number,
            challenge.series_best_of,
        )
    return (
        opponent_wins,
        creator_wins,
        challenge.series_game_number,
        challenge.series_best_of,
    )
