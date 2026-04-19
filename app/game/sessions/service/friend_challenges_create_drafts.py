from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED, DUEL_TYPE_DIRECT

from .friend_challenges_create_draft import FriendChallengeCreationDraft
from .friend_challenges_create_rematch_series import resolve_friend_challenge_rematch_series_state
from .friend_challenges_create_seed_state import load_friend_challenge_create_seed_state
from .friend_challenges_create_standard_draft import (
    build_create_friend_challenge_draft as build_standard_friend_challenge_draft,
)


async def build_create_friend_challenge_draft(
    session: AsyncSession,
    *,
    creator_user_id: int,
    challenge_type: str,
    mode_code: str,
    total_rounds: int,
    now_utc: datetime,
) -> FriendChallengeCreationDraft:
    return await build_standard_friend_challenge_draft(
        session,
        creator_user_id=creator_user_id,
        challenge_type=challenge_type,
        mode_code=mode_code,
        total_rounds=total_rounds,
        now_utc=now_utc,
    )


async def build_rematch_friend_challenge_draft(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    initiator_user_id: int,
    opponent_user_id: int | None,
    now_utc: datetime,
) -> FriendChallengeCreationDraft:
    series_state = await resolve_friend_challenge_rematch_series_state(
        session,
        challenge=challenge,
    )
    seed_state = await load_friend_challenge_create_seed_state(
        session,
        creator_user_id=initiator_user_id,
        mode_code=challenge.mode_code,
        total_rounds=challenge.total_rounds,
        now_utc=now_utc,
    )
    return FriendChallengeCreationDraft(
        challenge_id=seed_state.challenge_id,
        creator_user_id=initiator_user_id,
        opponent_user_id=opponent_user_id,
        challenge_type=DUEL_TYPE_DIRECT,
        mode_code=challenge.mode_code,
        access_type=seed_state.access_type,
        total_rounds=challenge.total_rounds,
        question_ids=seed_state.question_ids,
        status=DUEL_STATUS_ACCEPTED,
        series_id=series_state.series_id,
        series_game_number=series_state.series_game_number,
        series_best_of=series_state.series_best_of,
    )
