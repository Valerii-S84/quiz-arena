from __future__ import annotations

from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_questions import QuizQuestion as QuizQuestionRecord
from app.game.questions.runtime_bank_filters import (
    filter_active_records,
    pick_from_pool,
    select_diverse_record,
)
from app.game.questions.runtime_bank_models import to_quiz_question
from app.game.questions.runtime_bank_pool import _get_pool_ids, _repo, clear_question_pool_cache
from app.game.questions.types import QuizQuestion


def _pick_from_pool(
    candidate_ids: Sequence[str],
    *,
    exclude_question_ids: Sequence[str],
    selection_seed: str,
) -> str | None:
    return pick_from_pool(
        candidate_ids,
        exclude_question_ids=exclude_question_ids,
        selection_seed=selection_seed,
    )


async def _list_active_records_by_id(
    session: AsyncSession,
    question_ids: Sequence[str],
) -> list[QuizQuestionRecord]:
    unique_ids = tuple(dict.fromkeys(question_ids))
    if not unique_ids:
        return []

    records = await _repo().list_by_ids(session, question_ids=unique_ids)
    return filter_active_records(records, ids=unique_ids)


async def _pick_diverse_from_pool(
    session: AsyncSession,
    candidate_ids: Sequence[str],
    *,
    exclude_question_ids: Sequence[str],
    previous_question_ids: Sequence[str],
    selection_seed: str,
) -> str | None:
    if not candidate_ids or not previous_question_ids:
        return None

    excluded = set(exclude_question_ids)
    eligible_ids = [question_id for question_id in candidate_ids if question_id not in excluded]
    fallback_to_duplicate = False
    if not eligible_ids:
        eligible_ids = list(candidate_ids)
        fallback_to_duplicate = True

    candidate_records = await _list_active_records_by_id(session, eligible_ids)
    if not candidate_records:
        return None

    previous_records = await _list_active_records_by_id(session, previous_question_ids)
    selected = select_diverse_record(
        candidate_records=candidate_records,
        previous_records=previous_records,
        selection_seed=selection_seed,
    )
    if selected is None:
        return None
    if not fallback_to_duplicate and selected.question_id in excluded:
        return None
    return selected.question_id


async def _pick_question_id_from_pool(
    session: AsyncSession,
    *,
    mode_code: str,
    recent_question_ids: Sequence[str],
    selection_seed: str,
    preferred_levels: tuple[str, ...] | None,
) -> str | None:
    candidate_ids = await _get_pool_ids(
        session,
        mode_code=mode_code,
        preferred_levels=preferred_levels,
    )
    selected_id = await _pick_diverse_from_pool(
        session,
        candidate_ids,
        exclude_question_ids=recent_question_ids,
        previous_question_ids=recent_question_ids,
        selection_seed=selection_seed,
    )
    if selected_id is None:
        selected_id = _pick_from_pool(
            candidate_ids,
            exclude_question_ids=recent_question_ids,
            selection_seed=selection_seed,
        )
    if selected_id is None:
        selected_id = _pick_from_pool(
            candidate_ids,
            exclude_question_ids=(),
            selection_seed=selection_seed,
        )
    return selected_id


def _allowed_levels_tuple(allowed_levels: Sequence[str] | None) -> tuple[str, ...] | None:
    if allowed_levels is None:
        return None
    return tuple(dict.fromkeys(level.strip().upper() for level in allowed_levels if level))


async def _select_candidate_id_once(
    session: AsyncSession,
    *,
    mode_code: str,
    recent_question_ids: Sequence[str],
    selection_seed: str,
    preferred_level: str | None,
    allowed_levels: Sequence[str] | None,
) -> str | None:
    allowed_levels_normalized = _allowed_levels_tuple(allowed_levels)
    preferred_levels = (
        (preferred_level,) if preferred_level is not None else allowed_levels_normalized
    )
    selected_id = await _pick_question_id_from_pool(
        session,
        mode_code=mode_code,
        recent_question_ids=recent_question_ids,
        selection_seed=selection_seed,
        preferred_levels=preferred_levels,
    )
    if (
        selected_id is None
        and preferred_levels is not None
        and allowed_levels_normalized is not None
    ):
        selected_id = await _pick_question_id_from_pool(
            session,
            mode_code=mode_code,
            recent_question_ids=recent_question_ids,
            selection_seed=selection_seed,
            preferred_levels=allowed_levels_normalized,
        )
    return selected_id


async def _pick_from_mode(
    session: AsyncSession,
    *,
    mode_code: str,
    recent_question_ids: Sequence[str],
    selection_seed: str,
    preferred_level: str | None,
    allowed_levels: Sequence[str] | None = None,
) -> QuizQuestion | None:
    selected_id = await _select_candidate_id_once(
        session,
        mode_code=mode_code,
        recent_question_ids=recent_question_ids,
        selection_seed=selection_seed,
        preferred_level=preferred_level,
        allowed_levels=allowed_levels,
    )
    if selected_id is None:
        return None

    repo = _repo()
    selected = await repo.get_by_id(session, selected_id)
    if selected is None:
        clear_question_pool_cache()
        retry_selected_id = await _select_candidate_id_once(
            session,
            mode_code=mode_code,
            recent_question_ids=recent_question_ids,
            selection_seed=selection_seed,
            preferred_level=preferred_level,
            allowed_levels=allowed_levels,
        )
        if retry_selected_id is None:
            return None
        selected = await repo.get_by_id(session, retry_selected_id)
        if selected is None:
            return None
    return to_quiz_question(selected)
