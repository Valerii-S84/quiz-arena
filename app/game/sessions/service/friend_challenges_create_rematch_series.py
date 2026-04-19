from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo import FriendChallengesRepo

from .friend_challenges_series_utils import _count_series_wins, _series_wins_needed


@dataclass(frozen=True, slots=True)
class FriendChallengeRematchSeriesState:
    series_id: UUID | None
    series_game_number: int
    series_best_of: int


async def resolve_friend_challenge_rematch_series_state(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
) -> FriendChallengeRematchSeriesState:
    series_id = challenge.series_id
    if series_id is None or challenge.series_best_of <= 1:
        return FriendChallengeRematchSeriesState(
            series_id=series_id,
            series_game_number=1,
            series_best_of=1,
        )

    series_challenges = await FriendChallengesRepo.list_by_series_id_for_update(
        session,
        series_id=series_id,
    )
    creator_wins, opponent_wins = _count_series_wins(
        series_challenges=series_challenges,
        creator_user_id=challenge.creator_user_id,
        opponent_user_id=challenge.opponent_user_id,
    )
    wins_needed = _series_wins_needed(best_of=challenge.series_best_of)
    max_wins = max(creator_wins, opponent_wins)
    max_game_number = max(
        (int(item.series_game_number) for item in series_challenges),
        default=int(challenge.series_game_number),
    )
    if max_wins < wins_needed and max_game_number < challenge.series_best_of:
        return FriendChallengeRematchSeriesState(
            series_id=series_id,
            series_game_number=max_game_number + 1,
            series_best_of=int(challenge.series_best_of),
        )
    return FriendChallengeRematchSeriesState(
        series_id=None,
        series_game_number=1,
        series_best_of=1,
    )
