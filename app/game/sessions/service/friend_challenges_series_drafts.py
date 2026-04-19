from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED, DUEL_TYPE_DIRECT
from app.game.sessions.errors import FriendChallengeAccessError

from .friend_challenges_access import _resolve_friend_challenge_access_type
from .friend_challenges_series_utils import _count_series_wins, _series_wins_needed


@dataclass(slots=True)
class FriendChallengeSeriesDraft:
    creator_user_id: int
    opponent_user_id: int | None
    challenge_type: str
    mode_code: str
    access_type: str
    total_rounds: int
    series_id: UUID
    series_game_number: int
    series_best_of: int
    status: str


async def _build_series_friend_challenge_draft(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    initiator_user_id: int,
    opponent_user_id: int | None,
    now_utc: datetime,
    series_id: UUID,
    series_game_number: int,
    series_best_of: int,
) -> FriendChallengeSeriesDraft:
    access_type = await _resolve_friend_challenge_access_type(
        session,
        creator_user_id=initiator_user_id,
        now_utc=now_utc,
    )
    return FriendChallengeSeriesDraft(
        creator_user_id=initiator_user_id,
        opponent_user_id=opponent_user_id,
        challenge_type=DUEL_TYPE_DIRECT,
        mode_code=challenge.mode_code,
        access_type=access_type,
        total_rounds=challenge.total_rounds,
        series_id=series_id,
        series_game_number=series_game_number,
        series_best_of=series_best_of,
        status=DUEL_STATUS_ACCEPTED,
    )


async def build_series_start_friend_challenge_draft(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    initiator_user_id: int,
    opponent_user_id: int | None,
    now_utc: datetime,
    best_of: int,
) -> FriendChallengeSeriesDraft:
    return await _build_series_friend_challenge_draft(
        session,
        challenge=challenge,
        initiator_user_id=initiator_user_id,
        opponent_user_id=opponent_user_id,
        now_utc=now_utc,
        series_id=uuid4(),
        series_game_number=1,
        series_best_of=max(1, int(best_of)),
    )


async def _resolve_series_next_game_state(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
) -> tuple[UUID, int, int]:
    if challenge.series_id is None or challenge.series_best_of <= 1:
        raise FriendChallengeAccessError

    series_challenges = await FriendChallengesRepo.list_by_series_id_for_update(
        session,
        series_id=challenge.series_id,
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
    if max_wins >= wins_needed or max_game_number >= challenge.series_best_of:
        raise FriendChallengeAccessError
    return challenge.series_id, max_game_number + 1, challenge.series_best_of


async def build_series_next_game_friend_challenge_draft(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    initiator_user_id: int,
    opponent_user_id: int | None,
    now_utc: datetime,
) -> FriendChallengeSeriesDraft:
    series_id, series_game_number, series_best_of = await _resolve_series_next_game_state(
        session,
        challenge=challenge,
    )
    return await _build_series_friend_challenge_draft(
        session,
        challenge=challenge,
        initiator_user_id=initiator_user_id,
        opponent_user_id=opponent_user_id,
        now_utc=now_utc,
        series_id=series_id,
        series_game_number=series_game_number,
        series_best_of=series_best_of,
    )
