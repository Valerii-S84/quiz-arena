from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.game.sessions.types import FriendChallengeRoundStartResult, StartSessionResult

from .friend_challenges_internal import _build_friend_challenge_snapshot
from .friend_challenges_round_start_session import (
    build_existing_round_start_result,
    start_new_round_session,
)
from .friend_challenges_rounds_state import (
    _FriendChallengeRoundContext,
    is_round_playable,
    load_friend_challenge_round_context,
)


def _build_round_start_result(
    context: _FriendChallengeRoundContext,
    *,
    start_result: StartSessionResult | None,
    waiting_for_opponent: bool,
    already_answered_current_round: bool,
) -> FriendChallengeRoundStartResult:
    return FriendChallengeRoundStartResult(
        snapshot=_build_friend_challenge_snapshot(context.challenge),
        start_result=start_result,
        waiting_for_opponent=waiting_for_opponent,
        already_answered_current_round=already_answered_current_round,
    )


async def start_friend_challenge_round(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    idempotency_key: str,
    now_utc: datetime,
) -> FriendChallengeRoundStartResult:
    context = await load_friend_challenge_round_context(
        session,
        challenge_id=challenge_id,
        user_id=user_id,
        now_utc=now_utc,
    )
    if context.next_round > context.challenge.total_rounds:
        return _build_round_start_result(
            context,
            start_result=None,
            waiting_for_opponent=is_round_playable(context),
            already_answered_current_round=True,
        )

    existing_round_session = await QuizSessionsRepo.get_by_friend_challenge_round_user(
        session,
        friend_challenge_id=context.challenge.id,
        friend_challenge_round=context.next_round,
        user_id=user_id,
    )
    if existing_round_session is not None:
        start_result = await build_existing_round_start_result(
            session,
            existing_round_session=existing_round_session,
            tournament_match_id=context.challenge.tournament_match_id,
        )
        return _build_round_start_result(
            context,
            start_result=start_result,
            waiting_for_opponent=False,
            already_answered_current_round=False,
        )

    start_result = await start_new_round_session(
        session,
        challenge=context.challenge,
        next_round=context.next_round,
        user_id=user_id,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )
    return _build_round_start_result(
        context,
        start_result=start_result,
        waiting_for_opponent=False,
        already_answered_current_round=False,
    )
