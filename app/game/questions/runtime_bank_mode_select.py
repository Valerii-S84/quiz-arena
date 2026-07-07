from __future__ import annotations

from datetime import date
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.questions.catalog import DAILY_CHALLENGE_SOURCE_MODE, mode_requires_quick_mix_eligible
from app.game.questions.runtime_bank_fallback import (
    fallback_get_question_by_id,
    fallback_get_question_for_mode,
    fallback_select_question_for_mode,
)
from app.game.questions.runtime_bank_mode_picker import _list_active_records_by_id, _pick_from_mode
from app.game.questions.runtime_bank_models import to_quiz_question
from app.game.questions.runtime_bank_pool import (
    _get_question_by_id_cache,
    _repo,
    _store_question_by_id_cache,
)
from app.game.questions.types import QuizQuestion

__all__ = [
    "_list_active_records_by_id",
    "_list_candidate_ids_for_mode",
    "_pick_from_mode",
    "get_question_by_id",
    "get_question_for_mode",
    "select_question_for_mode",
]


async def _list_candidate_ids_for_mode(
    session: AsyncSession,
    *,
    mode_code: str,
    exclude_question_ids: Sequence[str] | None,
    preferred_levels: Sequence[str] | None,
) -> list[str]:
    repo = _repo()
    if mode_requires_quick_mix_eligible(mode_code):
        return await repo.list_question_ids_all_active(
            session,
            exclude_question_ids=exclude_question_ids,
            preferred_levels=preferred_levels,
            require_quick_mix_eligible=True,
        )
    return await repo.list_question_ids_for_mode(
        session,
        mode_code=mode_code,
        exclude_question_ids=exclude_question_ids,
        preferred_levels=preferred_levels,
    )


async def get_question_by_id(
    session: AsyncSession,
    mode_code: str,
    *,
    question_id: str,
    local_date_berlin: date,
) -> QuizQuestion | None:
    cached = _get_question_by_id_cache(question_id)
    if cached is not None:
        return cached

    selected = await _repo().get_by_id(session, question_id)
    if selected is not None and selected.status == "ACTIVE":
        question = to_quiz_question(selected)
        _store_question_by_id_cache(question)
        return question
    return fallback_get_question_by_id(
        mode_code,
        question_id=question_id,
        local_date_berlin=local_date_berlin,
    )


async def select_question_for_mode(
    session: AsyncSession,
    mode_code: str,
    *,
    local_date_berlin: date,
    recent_question_ids: Sequence[str],
    selection_seed: str,
    preferred_level: str | None = None,
    allowed_levels: Sequence[str] | None = None,
) -> QuizQuestion:
    db_mode_code = DAILY_CHALLENGE_SOURCE_MODE if mode_code == "DAILY_CHALLENGE" else mode_code
    db_seed = (
        f"daily:{local_date_berlin.isoformat()}:{db_mode_code}"
        if mode_code == "DAILY_CHALLENGE"
        else selection_seed
    )
    db_recent = () if mode_code == "DAILY_CHALLENGE" else recent_question_ids
    selected = await _pick_from_mode(
        session,
        mode_code=db_mode_code,
        recent_question_ids=db_recent,
        selection_seed=db_seed,
        preferred_level=preferred_level,
        allowed_levels=allowed_levels,
    )
    if selected is not None:
        return selected

    return fallback_select_question_for_mode(
        mode_code,
        local_date_berlin=local_date_berlin,
        recent_question_ids=recent_question_ids,
        selection_seed=selection_seed,
        preferred_level=preferred_level,
        allowed_levels=allowed_levels,
    )


async def get_question_for_mode(
    session: AsyncSession,
    mode_code: str,
    *,
    local_date_berlin: date,
) -> QuizQuestion:
    selected = await select_question_for_mode(
        session,
        mode_code,
        local_date_berlin=local_date_berlin,
        recent_question_ids=(),
        selection_seed=f"fallback:{mode_code}:{local_date_berlin.isoformat()}",
        preferred_level=None,
    )
    if selected is not None:
        return selected
    return fallback_get_question_for_mode(mode_code, local_date_berlin=local_date_berlin)
