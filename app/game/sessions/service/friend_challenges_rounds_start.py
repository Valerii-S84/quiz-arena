from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.streak.time import berlin_local_date
from app.game.sessions.types import StartSessionResult

from .levels import _friend_challenge_level_for_round
from .question_loading import _build_start_result_from_existing_session
from .sessions_start import start_session


async def build_existing_friend_challenge_round_start(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    user_id: int,
    next_round: int,
    header_mode_label_override: str | None,
) -> StartSessionResult | None:
    existing_round_session = await QuizSessionsRepo.get_by_friend_challenge_round_user(
        session,
        friend_challenge_id=challenge.id,
        friend_challenge_round=next_round,
        user_id=user_id,
    )
    if existing_round_session is None:
        return None

    start_result = await _build_start_result_from_existing_session(
        session,
        existing=existing_round_session,
        idempotent_replay=True,
    )
    start_result.session.header_mode_label_override = header_mode_label_override
    return start_result


async def start_new_friend_challenge_round_session(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    user_id: int,
    next_round: int,
    idempotency_key: str,
    now_utc: datetime,
    header_mode_label_override: str | None,
) -> StartSessionResult:
    selection_seed = f"friend:{challenge.id}:{next_round}:{challenge.mode_code}"
    preferred_level = _friend_challenge_level_for_round(round_number=next_round)
    forced_question_id = await _resolve_forced_question_id(
        session,
        challenge=challenge,
        next_round=next_round,
        selection_seed=selection_seed,
        preferred_level=preferred_level,
        now_utc=now_utc,
    )
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
    start_result.session.header_mode_label_override = header_mode_label_override
    return start_result


async def _resolve_forced_question_id(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    next_round: int,
    selection_seed: str,
    preferred_level: str | None,
    now_utc: datetime,
) -> str:
    shared_round_session = await QuizSessionsRepo.get_by_friend_challenge_round_any_user(
        session,
        friend_challenge_id=challenge.id,
        friend_challenge_round=next_round,
    )
    forced_question_id = shared_round_session.question_id if shared_round_session else None
    if forced_question_id is None and challenge.question_ids:
        forced_question_id = _planned_question_id(challenge=challenge, next_round=next_round)
    if forced_question_id is not None:
        return str(forced_question_id)
    return await _select_new_round_question_id(
        session,
        challenge=challenge,
        next_round=next_round,
        selection_seed=selection_seed,
        preferred_level=preferred_level,
        now_utc=now_utc,
    )


def _planned_question_id(*, challenge: FriendChallenge, next_round: int) -> str | None:
    if challenge.question_ids is None:
        return None
    try:
        return str(challenge.question_ids[next_round - 1])
    except IndexError:
        return None


async def _select_new_round_question_id(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    next_round: int,
    selection_seed: str,
    preferred_level: str | None,
    now_utc: datetime,
) -> str:
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
    return selected_question.question_id
