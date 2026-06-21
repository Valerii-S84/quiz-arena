from __future__ import annotations

import asyncio
from time import monotonic

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.repo.quiz_questions_repo import QuizQuestionPoolCandidate
from app.game.questions.runtime_bank_pool_entries import PoolCacheEntry as _PoolCacheEntry
from app.game.questions.runtime_bank_pool_entries import QuestionCacheEntry as _QuestionCacheEntry
from app.game.questions.runtime_bank_pool_entries import (
    build_full_pool_entry as _build_full_pool_entry,
)
from app.game.questions.runtime_bank_pool_entries import (
    build_incremental_pool_entry as _build_incremental_pool_entry,
)
from app.game.questions.runtime_bank_pool_loader import (  # noqa: F401
    load_pool_candidates as _load_pool_candidates,
)
from app.game.questions.runtime_bank_pool_loader import (  # noqa: F401
    load_pool_ids as _load_pool_ids,
)
from app.game.questions.runtime_bank_pool_membership import pool_cache_scope as _pool_cache_scope
from app.game.questions.runtime_bank_pool_membership import (
    question_from_pool_candidate as _question_from_pool_candidate,
)
from app.game.questions.types import QuizQuestion

_QUESTION_POOL_CACHE: dict[tuple[str, tuple[str, ...] | None], _PoolCacheEntry] = {}
_QUESTION_BY_ID_CACHE: dict[str, _QuestionCacheEntry] = {}
_QUESTION_POOL_CACHE_LOCK = asyncio.Lock()


def _repo():
    from app.game.questions import runtime_bank

    return runtime_bank.QuizQuestionsRepo


def _clamp_cache_ttl_seconds(value: int) -> int:
    return max(1, min(3600, int(value)))


def clear_question_pool_cache() -> None:
    _QUESTION_POOL_CACHE.clear()
    _QUESTION_BY_ID_CACHE.clear()


def _get_question_by_id_cache(question_id: str) -> QuizQuestion | None:
    cached = _QUESTION_BY_ID_CACHE.get(question_id)
    if cached is None:
        return None
    ttl_seconds = _clamp_cache_ttl_seconds(get_settings().quiz_question_pool_cache_ttl_seconds)
    if (monotonic() - cached.loaded_at_mono) > ttl_seconds:
        _QUESTION_BY_ID_CACHE.pop(question_id, None)
        return None
    return cached.question


def _store_question_by_id_cache(question: QuizQuestion) -> None:
    _QUESTION_BY_ID_CACHE[question.question_id] = _QuestionCacheEntry(
        loaded_at_mono=monotonic(),
        question=question,
    )


async def _get_pool_ids(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> tuple[str, ...]:
    entry = await _get_pool_entry(
        session,
        mode_code=mode_code,
        preferred_levels=preferred_levels,
    )
    return entry.question_ids


async def _get_pool_candidates(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> tuple[QuizQuestionPoolCandidate, ...]:
    entry = await _get_pool_entry(
        session,
        mode_code=mode_code,
        preferred_levels=preferred_levels,
    )
    return tuple(entry.candidates_by_id[question_id] for question_id in entry.question_ids)


async def _get_pool_question(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
    question_id: str,
) -> QuizQuestion | None:
    entry = await _get_pool_entry(
        session,
        mode_code=mode_code,
        preferred_levels=preferred_levels,
    )
    candidate = entry.candidates_by_id.get(question_id)
    if candidate is None:
        return None
    return _question_from_pool_candidate(candidate)


async def _get_pool_entry(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> _PoolCacheEntry:
    cache_key = (_pool_cache_scope(mode_code), preferred_levels)
    ttl_seconds = _clamp_cache_ttl_seconds(get_settings().quiz_question_pool_cache_ttl_seconds)
    now_mono = monotonic()
    cached = _QUESTION_POOL_CACHE.get(cache_key)
    if cached is not None and (now_mono - cached.loaded_at_mono) <= ttl_seconds:
        return cached

    async with _QUESTION_POOL_CACHE_LOCK:
        cached = _QUESTION_POOL_CACHE.get(cache_key)
        if cached is not None and (now_mono - cached.loaded_at_mono) <= ttl_seconds:
            return cached

        updated_entry = (
            await _build_incremental_pool_entry(
                session,
                mode_code=mode_code,
                preferred_levels=preferred_levels,
                cached=cached,
                question_cache=_QUESTION_BY_ID_CACHE,
                loaded_at_mono=monotonic,
            )
            if cached is not None
            else await _build_full_pool_entry(
                session,
                mode_code=mode_code,
                preferred_levels=preferred_levels,
                loaded_at_mono=monotonic,
            )
        )
        _QUESTION_POOL_CACHE[cache_key] = updated_entry
        return updated_entry
