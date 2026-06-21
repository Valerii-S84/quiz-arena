from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.questions.runtime_bank_diverse_picker import _list_active_records_by_id  # noqa: F401
from app.game.questions.runtime_bank_diverse_picker import _pick_diverse_from_pool, _pick_from_pool
from app.game.questions.runtime_bank_models import to_quiz_question
from app.game.questions.runtime_bank_pool import (
    _get_pool_candidates,
    _get_pool_ids,
    _get_pool_question,
    _get_question_by_id_cache,
    _repo,
    _store_question_by_id_cache,
    clear_question_pool_cache,
)
from app.game.questions.types import QuizQuestion


async def _pick_question_id_from_pool(
    session: AsyncSession,
    *,
    mode_code: str,
    recent_question_ids: Sequence[str],
    selection_seed: str,
    preferred_levels: tuple[str, ...] | None,
) -> str | None:
    if not recent_question_ids:
        candidate_ids = await _get_pool_ids(
            session,
            mode_code=mode_code,
            preferred_levels=preferred_levels,
        )
        return _pick_from_pool(
            candidate_ids,
            exclude_question_ids=(),
            selection_seed=selection_seed,
        )

    candidate_pool = await _get_pool_candidates(
        session,
        mode_code=mode_code,
        preferred_levels=preferred_levels,
    )
    candidate_ids = tuple(candidate.question_id for candidate in candidate_pool)
    selected_id = await _pick_diverse_from_pool(
        session,
        candidate_pool,
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
    normalized_levels = tuple(
        dict.fromkeys(level.strip().upper() for level in allowed_levels if level and level.strip())
    )
    return normalized_levels or None


async def _select_candidate_id_once(
    session: AsyncSession,
    *,
    mode_code: str,
    recent_question_ids: Sequence[str],
    selection_seed: str,
    preferred_level: str | None,
    allowed_levels: Sequence[str] | None,
) -> tuple[str | None, tuple[str, ...] | None]:
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
    selected_preferred_levels = preferred_levels
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
        selected_preferred_levels = allowed_levels_normalized
    return selected_id, selected_preferred_levels


async def _pick_from_mode(
    session: AsyncSession,
    *,
    mode_code: str,
    recent_question_ids: Sequence[str],
    selection_seed: str,
    preferred_level: str | None,
    allowed_levels: Sequence[str] | None = None,
) -> QuizQuestion | None:
    selected_id, selected_preferred_levels = await _select_candidate_id_once(
        session,
        mode_code=mode_code,
        recent_question_ids=recent_question_ids,
        selection_seed=selection_seed,
        preferred_level=preferred_level,
        allowed_levels=allowed_levels,
    )
    if selected_id is None:
        return None

    cached = _get_question_by_id_cache(selected_id)
    if cached is not None:
        return cached

    pool_question = await _get_pool_question(
        session,
        mode_code=mode_code,
        preferred_levels=selected_preferred_levels,
        question_id=selected_id,
    )
    if pool_question is not None:
        _store_question_by_id_cache(pool_question)
        return pool_question

    repo = _repo()
    selected = await repo.get_by_id(session, selected_id)
    if selected is None:
        clear_question_pool_cache()
        retry_selected_id, _ = await _select_candidate_id_once(
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
    question = to_quiz_question(selected)
    _store_question_by_id_cache(question)
    return question
