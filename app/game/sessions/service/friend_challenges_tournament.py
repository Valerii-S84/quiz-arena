from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED, DUEL_TYPE_DIRECT
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _create_friend_challenge_row,
)
from .friend_challenges_question_plan import resolve_duel_rounds, select_duel_question_ids


async def create_tournament_match_friend_challenge(
    session: AsyncSession,
    *,
    creator_user_id: int,
    opponent_user_id: int,
    mode_code: str,
    total_rounds: int,
    tournament_match_id: UUID,
    now_utc: datetime,
    expires_at: datetime | None = None,
) -> FriendChallengeSnapshot:
    resolved_rounds = resolve_duel_rounds(total_rounds=total_rounds)
    challenge_id = uuid4()
    question_ids = await select_duel_question_ids(
        session,
        mode_code=mode_code,
        total_rounds=resolved_rounds,
        now_utc=now_utc,
        challenge_seed=str(challenge_id),
    )
    challenge = await _create_friend_challenge_row(
        session,
        challenge_id=challenge_id,
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        challenge_type=DUEL_TYPE_DIRECT,
        mode_code=mode_code,
        access_type="FREE",
        total_rounds=resolved_rounds,
        now_utc=now_utc,
        question_ids=question_ids,
        status=DUEL_STATUS_ACCEPTED,
    )
    challenge.tournament_match_id = tournament_match_id
    if expires_at is not None:
        challenge.expires_at = expires_at
    challenge.updated_at = now_utc
    return _build_friend_challenge_snapshot(challenge)
