from __future__ import annotations

from datetime import date
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.questions.catalog import DAILY_CHALLENGE_SOURCE_MODE
from app.game.questions.runtime_bank_filters import (
    filter_active_records,
    select_least_used_by_category,
)
from app.game.questions.runtime_bank_mode_select import (
    _list_candidate_ids_for_mode,
    select_question_for_mode,
)
from app.game.questions.runtime_bank_models import to_quiz_question
from app.game.questions.runtime_bank_pool import _repo
from app.game.questions.types import QuizQuestion


async def select_friend_challenge_question(
    session: AsyncSession,
    mode_code: str,
    *,
    local_date_berlin: date,
    previous_round_question_ids: Sequence[str],
    selection_seed: str,
    preferred_level: str | None,
) -> QuizQuestion:
    db_mode_code = DAILY_CHALLENGE_SOURCE_MODE if mode_code == "DAILY_CHALLENGE" else mode_code
    preferred_levels = (preferred_level,) if preferred_level is not None else None

    candidate_ids = await _list_candidate_ids_for_mode(
        session,
        mode_code=db_mode_code,
        exclude_question_ids=previous_round_question_ids,
        preferred_levels=preferred_levels,
    )
    if not candidate_ids:
        candidate_ids = await _list_candidate_ids_for_mode(
            session,
            mode_code=db_mode_code,
            exclude_question_ids=None,
            preferred_levels=preferred_levels,
        )
    if not candidate_ids and preferred_levels is not None:
        candidate_ids = await _list_candidate_ids_for_mode(
            session,
            mode_code=db_mode_code,
            exclude_question_ids=previous_round_question_ids,
            preferred_levels=None,
        )
    if not candidate_ids and preferred_levels is not None:
        candidate_ids = await _list_candidate_ids_for_mode(
            session,
            mode_code=db_mode_code,
            exclude_question_ids=None,
            preferred_levels=None,
        )

    if candidate_ids:
        repo = _repo()
        candidate_records = filter_active_records(
            await repo.list_by_ids(session, question_ids=candidate_ids),
            ids=candidate_ids,
        )
        if candidate_records:
            previous_records = await repo.list_by_ids(
                session,
                question_ids=list(previous_round_question_ids),
            )
            selected = select_least_used_by_category(
                candidate_records=candidate_records,
                previous_records=previous_records,
                selection_seed=selection_seed,
            )
            if selected is not None:
                return to_quiz_question(selected)

    return await select_question_for_mode(
        session,
        mode_code,
        local_date_berlin=local_date_berlin,
        recent_question_ids=previous_round_question_ids,
        selection_seed=selection_seed,
        preferred_level=preferred_level,
    )
