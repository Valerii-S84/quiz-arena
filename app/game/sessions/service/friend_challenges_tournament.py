from __future__ import annotations

from datetime import datetime
from typing import Sequence
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED, DUEL_TYPE_DIRECT
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_question_plan import resolve_duel_rounds, select_duel_question_ids
from .friend_challenges_records import (
    _build_friend_challenge_snapshot,
    _create_friend_challenge_row,
)


async def _tournament_match_question_ids(
    session: AsyncSession,
    *,
    challenge_id: UUID,
    tournament_id: UUID | None,
    tournament_round_no: int | None,
    mode_code: str,
    resolved_rounds: int,
    now_utc: datetime,
    preferred_levels_by_round: Sequence[str] | None,
) -> list[str]:
    return await select_duel_question_ids(
        session,
        mode_code=mode_code,
        total_rounds=resolved_rounds,
        now_utc=now_utc,
        challenge_seed=str(challenge_id),
        tournament_id=tournament_id,
        tournament_round_no=tournament_round_no,
        preferred_levels_by_round=preferred_levels_by_round,
    )


async def _tournament_match_challenge(
    session: AsyncSession,
    *,
    challenge_id: UUID,
    creator_user_id: int,
    opponent_user_id: int,
    mode_code: str,
    resolved_rounds: int,
    now_utc: datetime,
    question_ids: list[str],
):
    return await _create_friend_challenge_row(
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


def _finalize_tournament_match_challenge(
    *,
    challenge,
    tournament_match_id: UUID,
    now_utc: datetime,
    expires_at: datetime | None,
) -> None:
    challenge.tournament_match_id = tournament_match_id
    if expires_at is not None:
        challenge.expires_at = expires_at
    challenge.updated_at = now_utc


def _tournament_match_snapshot(
    challenge,
    tournament_match_id: UUID,
    now_utc: datetime,
    expires_at: datetime | None,
) -> FriendChallengeSnapshot:
    _finalize_tournament_match_challenge(
        challenge=challenge,
        tournament_match_id=tournament_match_id,
        now_utc=now_utc,
        expires_at=expires_at,
    )
    return _build_friend_challenge_snapshot(challenge)


async def create_tournament_match_friend_challenge(
    session: AsyncSession,
    *,
    creator_user_id: int,
    opponent_user_id: int,
    tournament_id: UUID | None = None,
    tournament_round_no: int | None = None,
    mode_code: str,
    total_rounds: int,
    tournament_match_id: UUID,
    now_utc: datetime,
    expires_at: datetime | None = None,
    preferred_levels_by_round: Sequence[str] | None = None,
) -> FriendChallengeSnapshot:
    resolved_rounds = resolve_duel_rounds(total_rounds=total_rounds)
    challenge_id = uuid4()
    question_ids = await _tournament_match_question_ids(
        session,
        challenge_id=challenge_id,
        tournament_id=tournament_id,
        tournament_round_no=tournament_round_no,
        mode_code=mode_code,
        resolved_rounds=resolved_rounds,
        now_utc=now_utc,
        preferred_levels_by_round=preferred_levels_by_round,
    )
    challenge = await _tournament_match_challenge(
        session,
        challenge_id=challenge_id,
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        mode_code=mode_code,
        resolved_rounds=resolved_rounds,
        now_utc=now_utc,
        question_ids=question_ids,
    )
    return _tournament_match_snapshot(challenge, tournament_match_id, now_utc, expires_at)
