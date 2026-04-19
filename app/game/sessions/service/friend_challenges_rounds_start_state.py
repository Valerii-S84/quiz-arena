from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.game.sessions.types import StartSessionResult

from .friend_challenges_round_start_session import (
    build_existing_round_start_result,
    start_new_round_session,
)
from .friend_challenges_rounds_state import (
    _FriendChallengeRoundContext,
    is_round_playable,
    load_friend_challenge_round_context,
)


@dataclass(slots=True)
class FriendChallengeRoundStartState:
    context: _FriendChallengeRoundContext
    start_result: StartSessionResult | None
    waiting_for_opponent: bool
    already_answered_current_round: bool


def _already_answered_round_start_state(
    *,
    context: _FriendChallengeRoundContext,
) -> FriendChallengeRoundStartState:
    return FriendChallengeRoundStartState(
        context=context,
        start_result=None,
        waiting_for_opponent=is_round_playable(context),
        already_answered_current_round=True,
    )


def _active_round_start_state(
    *,
    context: _FriendChallengeRoundContext,
    start_result: StartSessionResult,
) -> FriendChallengeRoundStartState:
    return FriendChallengeRoundStartState(
        context=context,
        start_result=start_result,
        waiting_for_opponent=False,
        already_answered_current_round=False,
    )


async def _existing_round_start_result(
    session: AsyncSession,
    *,
    context: _FriendChallengeRoundContext,
    user_id: int,
) -> StartSessionResult | None:
    existing_round_session = await QuizSessionsRepo.get_by_friend_challenge_round_user(
        session,
        friend_challenge_id=context.challenge.id,
        friend_challenge_round=context.next_round,
        user_id=user_id,
    )
    if existing_round_session is None:
        return None
    return await build_existing_round_start_result(
        session,
        existing_round_session=existing_round_session,
        tournament_match_id=context.challenge.tournament_match_id,
    )


async def _new_round_start_result(
    session: AsyncSession,
    *,
    context: _FriendChallengeRoundContext,
    user_id: int,
    idempotency_key: str,
    now_utc: datetime,
) -> StartSessionResult:
    return await start_new_round_session(
        session,
        challenge=context.challenge,
        next_round=context.next_round,
        user_id=user_id,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )


async def load_friend_challenge_round_start_state(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    idempotency_key: str,
    now_utc: datetime,
) -> FriendChallengeRoundStartState:
    context = await load_friend_challenge_round_context(
        session,
        challenge_id=challenge_id,
        user_id=user_id,
        now_utc=now_utc,
    )
    if context.next_round > context.challenge.total_rounds:
        return _already_answered_round_start_state(context=context)

    start_result = await _existing_round_start_result(
        session,
        context=context,
        user_id=user_id,
    )
    if start_result is not None:
        return _active_round_start_state(
            context=context,
            start_result=start_result,
        )

    start_result = await _new_round_start_result(
        session,
        user_id=user_id,
        context=context,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )
    return _active_round_start_state(
        context=context,
        start_result=start_result,
    )
