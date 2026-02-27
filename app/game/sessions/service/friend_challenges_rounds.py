from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.streak.time import berlin_local_date
from app.game.friend_challenges.constants import (
    is_duel_playable_status,
    normalize_duel_status,
)
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.types import FriendChallengeRoundStartResult

from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)
from .levels import _friend_challenge_level_for_round
from .question_loading import _build_start_result_from_existing_session
from .sessions_start import start_session


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
    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=challenge.opponent_user_id is not None,
    )
    if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
        )
    if challenge.status == "EXPIRED":
        raise FriendChallengeExpiredError
    if not is_duel_playable_status(challenge.status):
        raise FriendChallengeCompletedError
    if challenge.opponent_user_id is None:
        raise FriendChallengeFullError
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
            waiting_for_opponent=is_duel_playable_status(challenge.status),
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
            waiting_for_opponent=False,
            already_answered_current_round=False,
        )

    shared_round_session = await QuizSessionsRepo.get_by_friend_challenge_round_any_user(
        session,
        friend_challenge_id=challenge.id,
        friend_challenge_round=next_round,
    )
    selection_seed = f"friend:{challenge.id}:{next_round}:{challenge.mode_code}"
    preferred_level = _friend_challenge_level_for_round(round_number=next_round)
    forced_question_id: str | None = shared_round_session.question_id if shared_round_session else None
    if forced_question_id is None and challenge.question_ids:
        try:
            forced_question_id = str(challenge.question_ids[next_round - 1])
        except IndexError:
            forced_question_id = None
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
        waiting_for_opponent=False,
        already_answered_current_round=False,
    )
