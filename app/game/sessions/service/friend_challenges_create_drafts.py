from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED, DUEL_TYPE_DIRECT

from .friend_challenges_access import _resolve_friend_challenge_access_type
from .friend_challenges_create_rematch_series import resolve_friend_challenge_rematch_series_state
from .friend_challenges_question_plan import select_duel_question_ids


@dataclass(slots=True)
class FriendChallengeCreationDraft:
    challenge_id: UUID
    creator_user_id: int
    opponent_user_id: int | None
    challenge_type: str
    mode_code: str
    access_type: str
    total_rounds: int
    question_ids: list[str]
    status: str
    series_id: UUID | None = None
    series_game_number: int = 1
    series_best_of: int = 1


async def build_create_friend_challenge_draft(
    session: AsyncSession,
    *,
    creator_user_id: int,
    challenge_type: str,
    mode_code: str,
    total_rounds: int,
    now_utc: datetime,
) -> FriendChallengeCreationDraft:
    access_type = await _resolve_friend_challenge_access_type(
        session,
        creator_user_id=creator_user_id,
        now_utc=now_utc,
    )
    challenge_id = uuid4()
    question_ids = await select_duel_question_ids(
        session,
        mode_code=mode_code,
        total_rounds=total_rounds,
        now_utc=now_utc,
        challenge_seed=str(challenge_id),
    )
    return FriendChallengeCreationDraft(
        challenge_id=challenge_id,
        creator_user_id=creator_user_id,
        opponent_user_id=None,
        challenge_type=challenge_type,
        mode_code=mode_code,
        access_type=access_type,
        total_rounds=total_rounds,
        question_ids=question_ids,
        status="PENDING",
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
    access_type = await _resolve_friend_challenge_access_type(
        session,
        creator_user_id=initiator_user_id,
        now_utc=now_utc,
    )
    challenge_id = uuid4()
    question_ids = await select_duel_question_ids(
        session,
        mode_code=challenge.mode_code,
        total_rounds=challenge.total_rounds,
        now_utc=now_utc,
        challenge_seed=str(challenge_id),
    )
    return FriendChallengeCreationDraft(
        challenge_id=challenge_id,
        creator_user_id=initiator_user_id,
        opponent_user_id=opponent_user_id,
        challenge_type=DUEL_TYPE_DIRECT,
        mode_code=challenge.mode_code,
        access_type=access_type,
        total_rounds=challenge.total_rounds,
        question_ids=question_ids,
        status=DUEL_STATUS_ACCEPTED,
        series_id=series_state.series_id,
        series_game_number=series_state.series_game_number,
        series_best_of=series_state.series_best_of,
    )
