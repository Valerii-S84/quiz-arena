from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED, DUEL_TYPE_DIRECT

from .friend_challenges_access import _resolve_friend_challenge_access_type
from .friend_challenges_series_next_game_state import load_friend_challenge_series_next_game_state


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


async def build_series_next_game_friend_challenge_draft(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    initiator_user_id: int,
    opponent_user_id: int | None,
    now_utc: datetime,
) -> FriendChallengeSeriesDraft:
    next_game_state = await load_friend_challenge_series_next_game_state(
        session,
        challenge=challenge,
    )
    return await _build_series_friend_challenge_draft(
        session,
        challenge=challenge,
        initiator_user_id=initiator_user_id,
        opponent_user_id=opponent_user_id,
        now_utc=now_utc,
        series_id=next_game_state.series_id,
        series_game_number=next_game_state.series_game_number,
        series_best_of=next_game_state.series_best_of,
    )
