from __future__ import annotations

import asyncio
from collections import Counter
import hashlib
from datetime import date
from time import monotonic
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.quiz_questions import QuizQuestion as QuizQuestionRecord
from app.db.repo.quiz_questions_repo import QuizQuestionsRepo
from app.game.questions.catalog import DAILY_CHALLENGE_SOURCE_MODE
from app.game.questions.static_bank import (
    get_question_by_id as get_question_by_id_fallback,
)
from app.game.questions.static_bank import (
    get_question_for_mode as get_question_for_mode_fallback,
)
from app.game.questions.static_bank import (
    select_question_for_mode as select_question_for_mode_fallback,
)
from app.game.questions.types import QuizQuestion

QUICK_MIX_MODE_CODE = "QUICK_MIX_A1A2"
ALL_ACTIVE_SCOPE_CODE = "__ALL_ACTIVE__"
_QUESTION_POOL_CACHE: dict[tuple[str, tuple[str, ...] | None], tuple[float, tuple[str, ...]]] = {}
_QUESTION_POOL_CACHE_LOCK = asyncio.Lock()


def _stable_index(seed: str, size: int) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % size


def _to_quiz_question(record: QuizQuestionRecord) -> QuizQuestion:
    return QuizQuestion(
        question_id=record.question_id,
        text=record.question_text,
        options=(
            record.option_1,
            record.option_2,
            record.option_3,
            record.option_4,
        ),
        correct_option=record.correct_option_id,
        level=record.level,
        category=record.category,
    )


def _clamp_cache_ttl_seconds(value: int) -> int:
    return max(1, min(3600, int(value)))


def clear_question_pool_cache() -> None:
    _QUESTION_POOL_CACHE.clear()


def _pool_cache_scope(mode_code: str) -> str:
    return ALL_ACTIVE_SCOPE_CODE if mode_code == QUICK_MIX_MODE_CODE else mode_code


async def _load_pool_ids(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if mode_code == QUICK_MIX_MODE_CODE:
        pool_ids = await QuizQuestionsRepo.list_question_ids_all_active(
            session,
            exclude_question_ids=None,
            preferred_levels=preferred_levels,
        )
    else:
        pool_ids = await QuizQuestionsRepo.list_question_ids_for_mode(
            session,
            mode_code=mode_code,
            exclude_question_ids=None,
            preferred_levels=preferred_levels,
        )
    return tuple(pool_ids)


async def _get_pool_ids(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> tuple[str, ...]:
    cache_key = (_pool_cache_scope(mode_code), preferred_levels)
    ttl_seconds = _clamp_cache_ttl_seconds(get_settings().quiz_question_pool_cache_ttl_seconds)
    now_mono = monotonic()
    cached = _QUESTION_POOL_CACHE.get(cache_key)
    if cached is not None and (now_mono - cached[0]) <= ttl_seconds:
        return cached[1]

    async with _QUESTION_POOL_CACHE_LOCK:
        cached = _QUESTION_POOL_CACHE.get(cache_key)
        if cached is not None and (now_mono - cached[0]) <= ttl_seconds:
            return cached[1]

        loaded_ids = await _load_pool_ids(
            session,
            mode_code=mode_code,
            preferred_levels=preferred_levels,
        )
        _QUESTION_POOL_CACHE[cache_key] = (monotonic(), loaded_ids)
        return loaded_ids


def _pick_from_pool(
    candidate_ids: Sequence[str],
    *,
    exclude_question_ids: Sequence[str],
    selection_seed: str,
) -> str | None:
    if not candidate_ids:
        return None
    if not exclude_question_ids:
        return candidate_ids[_stable_index(selection_seed, len(candidate_ids))]

    excluded = set(exclude_question_ids)
    if len(excluded) >= len(candidate_ids):
        return None

    start_index = _stable_index(selection_seed, len(candidate_ids))
    for offset in range(len(candidate_ids)):
        candidate_id = candidate_ids[(start_index + offset) % len(candidate_ids)]
        if candidate_id not in excluded:
            return candidate_id
    return None


async def _list_candidate_ids_for_mode(
    session: AsyncSession,
    *,
    mode_code: str,
    exclude_question_ids: Sequence[str] | None,
    preferred_levels: Sequence[str] | None,
) -> list[str]:
    if mode_code == QUICK_MIX_MODE_CODE:
        return await QuizQuestionsRepo.list_question_ids_all_active(
            session,
            exclude_question_ids=exclude_question_ids,
            preferred_levels=preferred_levels,
        )
    return await QuizQuestionsRepo.list_question_ids_for_mode(
        session,
        mode_code=mode_code,
        exclude_question_ids=exclude_question_ids,
        preferred_levels=preferred_levels,
    )


async def _pick_from_mode(
    session: AsyncSession,
    *,
    mode_code: str,
    recent_question_ids: Sequence[str],
    selection_seed: str,
    preferred_level: str | None,
) -> QuizQuestion | None:
    async def _select_candidate_id_once() -> str | None:
        preferred_levels = (preferred_level,) if preferred_level is not None else None
        candidate_ids = await _get_pool_ids(
            session,
            mode_code=mode_code,
            preferred_levels=preferred_levels,
        )
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

        if selected_id_local is None and preferred_levels is not None:
            fallback_candidate_ids = await _get_pool_ids(
                session,
                mode_code=mode_code,
                preferred_levels=None,
            )
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

    selected = await QuizQuestionsRepo.get_by_id(session, selected_id)
    if selected is None:
        clear_question_pool_cache()
        retry_selected_id = await _select_candidate_id_once()
        if retry_selected_id is None:
            return None
        selected = await QuizQuestionsRepo.get_by_id(session, retry_selected_id)
        if selected is None:
            return None
    return _to_quiz_question(selected)


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

    def _filtered_records(
        all_records: Sequence[QuizQuestionRecord],
        *,
        ids: Sequence[str],
    ) -> list[QuizQuestionRecord]:
        by_id = {record.question_id: record for record in all_records}
        ordered: list[QuizQuestionRecord] = []
        for question_id in ids:
            record = by_id.get(question_id)
            if record is not None and record.status == "ACTIVE":
                ordered.append(record)
        return ordered

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
        candidate_records = _filtered_records(
            await QuizQuestionsRepo.list_by_ids(session, question_ids=candidate_ids),
            ids=candidate_ids,
        )
        if candidate_records:
            previous_records = await QuizQuestionsRepo.list_by_ids(
                session,
                question_ids=list(previous_round_question_ids),
            )
            category_counts: Counter[str] = Counter()
            for record in previous_records:
                category_counts[record.category] += 1

            min_count = min(category_counts.get(record.category, 0) for record in candidate_records)
            least_used_candidates = [
                record
                for record in candidate_records
                if category_counts.get(record.category, 0) == min_count
            ]
            least_used_candidates.sort(key=lambda record: record.question_id)
            selected = least_used_candidates[
                _stable_index(selection_seed, len(least_used_candidates))
            ]
            return _to_quiz_question(selected)

    return await select_question_for_mode(
        session,
        mode_code,
        local_date_berlin=local_date_berlin,
        recent_question_ids=previous_round_question_ids,
        selection_seed=selection_seed,
        preferred_level=preferred_level,
    )


async def get_question_by_id(
    session: AsyncSession,
    mode_code: str,
    *,
    question_id: str,
    local_date_berlin: date,
) -> QuizQuestion | None:
    selected = await QuizQuestionsRepo.get_by_id(session, question_id)
    if selected is not None and selected.status == "ACTIVE":
        return _to_quiz_question(selected)
    return get_question_by_id_fallback(
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
    )
    if selected is not None:
        return selected

    return select_question_for_mode_fallback(
        mode_code,
        local_date_berlin=local_date_berlin,
        recent_question_ids=recent_question_ids,
        selection_seed=selection_seed,
        preferred_level=preferred_level,
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
    return get_question_for_mode_fallback(mode_code, local_date_berlin=local_date_berlin)
