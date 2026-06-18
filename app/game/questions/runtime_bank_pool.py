from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.repo.quiz_questions_repo import QuizQuestionPoolCandidate
from app.game.questions.catalog import mode_requires_quick_mix_eligible
from app.game.questions.runtime_bank_models import QUICK_MIX_MODE_CODE, QUICK_MIX_SCOPE_CODE
from app.game.questions.types import QuizQuestion


@dataclass(slots=True)
class _PoolCacheEntry:
    loaded_at_mono: float
    question_ids: tuple[str, ...]
    candidates_by_id: dict[str, QuizQuestionPoolCandidate]
    updated_at_watermark: datetime


@dataclass(slots=True)
class _QuestionCacheEntry:
    loaded_at_mono: float
    question: QuizQuestion


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


def _pool_cache_scope(mode_code: str) -> str:
    return QUICK_MIX_SCOPE_CODE if mode_code == QUICK_MIX_MODE_CODE else mode_code


def _pool_matches_mode(
    mode_code: str,
    *,
    question_mode_code: str,
    question_quick_mix_eligible: bool,
) -> bool:
    if mode_code == QUICK_MIX_MODE_CODE:
        return question_quick_mix_eligible
    return question_mode_code == mode_code


def _pool_matches_level(
    preferred_levels: tuple[str, ...] | None,
    *,
    question_level: str,
) -> bool:
    return preferred_levels is None or question_level in preferred_levels


def _pool_includes_question(
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
    *,
    question_mode_code: str,
    question_level: str,
    question_status: str,
    question_quick_mix_eligible: bool,
) -> bool:
    return (
        question_status == "ACTIVE"
        and _pool_matches_mode(
            mode_code,
            question_mode_code=question_mode_code,
            question_quick_mix_eligible=question_quick_mix_eligible,
        )
        and _pool_matches_level(preferred_levels, question_level=question_level)
    )


async def _load_pool_ids(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> tuple[str, ...]:
    return tuple(
        candidate.question_id
        for candidate in await _load_pool_candidates(
            session,
            mode_code=mode_code,
            preferred_levels=preferred_levels,
        )
    )


async def _load_pool_candidates(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> tuple[QuizQuestionPoolCandidate, ...]:
    repo = _repo()
    if mode_requires_quick_mix_eligible(mode_code):
        candidates = await repo.list_question_candidates_all_active(
            session,
            exclude_question_ids=None,
            preferred_levels=preferred_levels,
            require_quick_mix_eligible=True,
        )
    else:
        candidates = await repo.list_question_candidates_for_mode(
            session,
            mode_code=mode_code,
            exclude_question_ids=None,
            preferred_levels=preferred_levels,
        )
    return tuple(candidates)


async def _build_full_pool_entry(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> _PoolCacheEntry:
    loaded_candidates = await _load_pool_candidates(
        session,
        mode_code=mode_code,
        preferred_levels=preferred_levels,
    )
    candidates_by_id = {candidate.question_id: candidate for candidate in loaded_candidates}
    return _PoolCacheEntry(
        loaded_at_mono=monotonic(),
        question_ids=tuple(candidate.question_id for candidate in loaded_candidates),
        candidates_by_id=candidates_by_id,
        updated_at_watermark=datetime.now(timezone.utc),
    )


async def _build_incremental_pool_entry(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
    cached: _PoolCacheEntry,
) -> _PoolCacheEntry:
    changes = await _repo().list_question_pool_changes_since(
        session,
        since_updated_at=cached.updated_at_watermark,
    )
    if not changes:
        return _PoolCacheEntry(
            loaded_at_mono=monotonic(),
            question_ids=cached.question_ids,
            updated_at_watermark=cached.updated_at_watermark,
        )

    refreshed_candidates = dict(cached.candidates_by_id)
    max_updated_at = cached.updated_at_watermark
    for change in changes:
        _QUESTION_BY_ID_CACHE.pop(change.question_id, None)
        source_file = getattr(change, "source_file", "")
        category = getattr(change, "category", "")
        include_question = _pool_includes_question(
            mode_code,
            preferred_levels,
            question_mode_code=change.mode_code,
            question_level=change.level,
            question_status=change.status,
            question_quick_mix_eligible=change.quick_mix_eligible,
        )
        if include_question:
            refreshed_candidates[change.question_id] = QuizQuestionPoolCandidate(
                question_id=change.question_id,
                level=change.level,
                source_file=source_file,
                category=category,
            )
        else:
            refreshed_candidates.pop(change.question_id, None)
        if change.updated_at > max_updated_at:
            max_updated_at = change.updated_at

    refreshed_ids = tuple(sorted(refreshed_candidates))
    return _PoolCacheEntry(
        loaded_at_mono=monotonic(),
        question_ids=refreshed_ids,
        candidates_by_id={
            question_id: refreshed_candidates[question_id] for question_id in refreshed_ids
        },
        updated_at_watermark=max_updated_at,
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
            )
            if cached is not None
            else await _build_full_pool_entry(
                session,
                mode_code=mode_code,
                preferred_levels=preferred_levels,
            )
        )
        _QUESTION_POOL_CACHE[cache_key] = updated_entry
        return updated_entry
