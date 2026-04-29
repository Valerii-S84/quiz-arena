from __future__ import annotations

from datetime import date
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_questions import QuizQuestion as QuizQuestionRecord
from app.game.questions.catalog import DAILY_CHALLENGE_SOURCE_MODE, mode_requires_quick_mix_eligible
from app.game.questions.runtime_bank_fallback import (
    fallback_get_question_by_id,
    fallback_get_question_for_mode,
    fallback_select_question_for_mode,
)
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


async def _pick_from_mode(
    session: AsyncSession,
    *,
    mode_code: str,
    recent_question_ids: Sequence[str],
    selection_seed: str,
    preferred_level: str | None,
    allowed_levels: Sequence[str] | None = None,
) -> QuizQuestion | None:
    async def _select_candidate_id_once() -> str | None:
        allowed_levels_tuple = (
            tuple(dict.fromkeys(level.strip().upper() for level in allowed_levels if level))
            if allowed_levels
            else None
        )
        preferred_levels = (
            (preferred_level,) if preferred_level is not None else allowed_levels_tuple
        )
        candidate_ids = await _get_pool_ids(
            session,
            mode_code=mode_code,
            preferred_levels=preferred_levels,
        )
        selected_id_local = await _pick_diverse_from_pool(
            session,
            candidate_ids,
            exclude_question_ids=recent_question_ids,
            previous_question_ids=recent_question_ids,
            selection_seed=selection_seed,
        )
        if selected_id_local is None:
            selected_id_local = _pick_from_pool(
                candidate_ids,
                exclude_question_ids=recent_question_ids,
                selection_seed=selection_seed,
            )
        if selected_id_local is None:
            selected_id_local = _pick_from_pool(
                candidate_ids,
                exclude_question_ids=(),
                selection_seed=selection_seed,
            )

        if (
            selected_id_local is None
            and preferred_levels is not None
            and allowed_levels_tuple is not None
        ):
            fallback_candidate_ids = await _get_pool_ids(
                session,
                mode_code=mode_code,
                preferred_levels=allowed_levels_tuple,
            )
            selected_id_local = await _pick_diverse_from_pool(
                session,
                fallback_candidate_ids,
                exclude_question_ids=recent_question_ids,
                previous_question_ids=recent_question_ids,
                selection_seed=selection_seed,
            )
            if selected_id_local is None:
                selected_id_local = _pick_from_pool(
                    fallback_candidate_ids,
                    exclude_question_ids=recent_question_ids,
                    selection_seed=selection_seed,
                )
            if selected_id_local is None:
                selected_id_local = _pick_from_pool(
                    fallback_candidate_ids,
                    exclude_question_ids=(),
                    selection_seed=selection_seed,
                )
        return selected_id_local

    selected_id = await _select_candidate_id_once()
    if selected_id is None:
        return None

    repo = _repo()
    selected = await repo.get_by_id(session, selected_id)
    if selected is None:
        clear_question_pool_cache()
        retry_selected_id = await _select_candidate_id_once()
        if retry_selected_id is None:
            return None
        selected = await repo.get_by_id(session, retry_selected_id)
        if selected is None:
            return None
    return to_quiz_question(selected)


async def get_question_by_id(
    session: AsyncSession,
    mode_code: str,
    *,
    question_id: str,
    local_date_berlin: date,
) -> QuizQuestion | None:
    selected = await _repo().get_by_id(session, question_id)
    if selected is not None and selected.status == "ACTIVE":
        return to_quiz_question(selected)
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
