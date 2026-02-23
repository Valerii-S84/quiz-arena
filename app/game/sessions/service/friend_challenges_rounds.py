from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.streak.time import berlin_local_date
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.types import FriendChallengeJoinResult, FriendChallengeRoundStartResult

from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)
from .levels import _friend_challenge_level_for_round
from .question_loading import _build_start_result_from_existing_session
from .sessions_start import start_session


async def join_friend_challenge_by_token(
    session: AsyncSession,
    *,
    user_id: int,
    invite_token: str,
    now_utc: datetime,
) -> FriendChallengeJoinResult:
    challenge = await FriendChallengesRepo.get_by_invite_token_for_update(session, invite_token)
    if challenge is None:
        raise FriendChallengeNotFoundError
    if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
        )
    if challenge.status == "EXPIRED":
        raise FriendChallengeExpiredError
    if challenge.status != "ACTIVE":
        raise FriendChallengeCompletedError

    if challenge.creator_user_id == user_id:
        return FriendChallengeJoinResult(
            snapshot=_build_friend_challenge_snapshot(challenge),
            joined_now=False,
        )

    if challenge.opponent_user_id is None:
        challenge.opponent_user_id = user_id
        challenge.updated_at = now_utc
        await emit_analytics_event(
            session,
            event_type="friend_challenge_joined",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=user_id,
            payload={
                "challenge_id": str(challenge.id),
                "creator_user_id": challenge.creator_user_id,
                "mode_code": challenge.mode_code,
                "total_rounds": challenge.total_rounds,
                "expires_at": challenge.expires_at.isoformat(),
                "series_id": (
                    str(challenge.series_id) if challenge.series_id is not None else None
                ),
                "series_game_number": challenge.series_game_number,
                "series_best_of": challenge.series_best_of,
            },
        )
        return FriendChallengeJoinResult(
            snapshot=_build_friend_challenge_snapshot(challenge),
            joined_now=True,
        )

    if challenge.opponent_user_id == user_id:
        return FriendChallengeJoinResult(
            snapshot=_build_friend_challenge_snapshot(challenge),
            joined_now=False,
        )

    raise FriendChallengeFullError


async def start_friend_challenge_round(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    idempotency_key: str,
    now_utc: datetime,
) -> FriendChallengeRoundStartResult:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError
    if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
        )
    if challenge.status == "EXPIRED":
        raise FriendChallengeExpiredError
    if challenge.status != "ACTIVE":
        raise FriendChallengeCompletedError
    if user_id not in {challenge.creator_user_id, challenge.opponent_user_id}:
        raise FriendChallengeAccessError

    participant_answered_round = (
        challenge.creator_answered_round
        if user_id == challenge.creator_user_id
        else challenge.opponent_answered_round
    )
    next_round = participant_answered_round + 1
    if next_round > challenge.total_rounds:
        return FriendChallengeRoundStartResult(
            snapshot=_build_friend_challenge_snapshot(challenge),
            start_result=None,
            waiting_for_opponent=challenge.status == "ACTIVE",
            already_answered_current_round=True,
        )

    existing_round_session = await QuizSessionsRepo.get_by_friend_challenge_round_user(
        session,
        friend_challenge_id=challenge.id,
        friend_challenge_round=next_round,
        user_id=user_id,
    )
    if existing_round_session is not None:
        start_result = await _build_start_result_from_existing_session(
            session,
            existing=existing_round_session,
            idempotent_replay=True,
        )
        return FriendChallengeRoundStartResult(
            snapshot=_build_friend_challenge_snapshot(challenge),
            start_result=start_result,
            waiting_for_opponent=challenge.opponent_user_id is None,
            already_answered_current_round=False,
        )

    shared_round_session = await QuizSessionsRepo.get_by_friend_challenge_round_any_user(
        session,
        friend_challenge_id=challenge.id,
        friend_challenge_round=next_round,
    )
    selection_seed = f"friend:{challenge.id}:{next_round}:{challenge.mode_code}"
    preferred_level = _friend_challenge_level_for_round(round_number=next_round)
    forced_question_id: str | None = (
        shared_round_session.question_id if shared_round_session is not None else None
    )
    if forced_question_id is None:
        previous_round_question_ids = (
            await QuizSessionsRepo.list_friend_challenge_question_ids_before_round(
                session,
                friend_challenge_id=challenge.id,
                before_round=next_round,
            )
        )
        from app.game.sessions import service as service_module

        selected_question = await service_module.select_friend_challenge_question(
            session,
            challenge.mode_code,
            local_date_berlin=berlin_local_date(now_utc),
            previous_round_question_ids=previous_round_question_ids,
            selection_seed=selection_seed,
            preferred_level=preferred_level,
        )
        forced_question_id = selected_question.question_id

    start_result = await start_session(
        session,
        user_id=user_id,
        mode_code=challenge.mode_code,
        source="FRIEND_CHALLENGE",
        idempotency_key=idempotency_key,
        now_utc=now_utc,
        selection_seed_override=selection_seed,
        preferred_question_level=preferred_level,
        forced_question_id=forced_question_id,
        friend_challenge_id=challenge.id,
        friend_challenge_round=next_round,
        friend_challenge_total_rounds=challenge.total_rounds,
    )
    return FriendChallengeRoundStartResult(
        snapshot=_build_friend_challenge_snapshot(challenge),
        start_result=start_result,
        waiting_for_opponent=challenge.opponent_user_id is None,
        already_answered_current_round=False,
    )
