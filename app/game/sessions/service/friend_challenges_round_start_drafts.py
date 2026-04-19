from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.streak.time import berlin_local_date

from .levels import _friend_challenge_level_for_round


@dataclass(slots=True)
class FriendChallengeRoundStartDraft:
    selection_seed: str
    preferred_level: str | None
    forced_question_id: str


def _selection_seed(
    *,
    challenge_id: UUID,
    next_round: int,
    mode_code: str,
) -> str:
    return f"friend:{challenge_id}:{next_round}:{mode_code}"


def _planned_question_id(
    *,
    challenge: FriendChallenge,
    next_round: int,
) -> str | None:
    question_ids = challenge.question_ids
    if not question_ids:
        return None
    try:
        return str(question_ids[next_round - 1])
    except IndexError:
        return None


async def _resolve_round_question_id(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    next_round: int,
    now_utc: datetime,
    selection_seed: str,
    preferred_level: str | None,
) -> str:
    shared_round_session = await QuizSessionsRepo.get_by_friend_challenge_round_any_user(
        session,
        friend_challenge_id=challenge.id,
        friend_challenge_round=next_round,
    )
    if shared_round_session is not None and shared_round_session.question_id is not None:
        return shared_round_session.question_id

    planned_question_id = _planned_question_id(
        challenge=challenge,
        next_round=next_round,
    )
    if planned_question_id is not None:
        return planned_question_id

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


async def build_friend_challenge_round_start_draft(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    next_round: int,
    now_utc: datetime,
) -> FriendChallengeRoundStartDraft:
    selection_seed = _selection_seed(
        challenge_id=challenge.id,
        next_round=next_round,
        mode_code=challenge.mode_code,
    )
    preferred_level = _friend_challenge_level_for_round(round_number=next_round)
    forced_question_id = await _resolve_round_question_id(
        session,
        challenge=challenge,
        next_round=next_round,
        now_utc=now_utc,
        selection_seed=selection_seed,
        preferred_level=preferred_level,
    )
    return FriendChallengeRoundStartDraft(
        selection_seed=selection_seed,
        preferred_level=preferred_level,
        forced_question_id=forced_question_id,
    )
