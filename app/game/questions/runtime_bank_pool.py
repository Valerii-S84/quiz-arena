from __future__ import annotations

import asyncio
from time import monotonic

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.game.questions.runtime_bank_models import ALL_ACTIVE_SCOPE_CODE, QUICK_MIX_MODE_CODE

_QUESTION_POOL_CACHE: dict[tuple[str, tuple[str, ...] | None], tuple[float, tuple[str, ...]]] = {}
_QUESTION_POOL_CACHE_LOCK = asyncio.Lock()


def _repo():
    from app.game.questions import runtime_bank

    return runtime_bank.QuizQuestionsRepo


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
    repo = _repo()
    if mode_code == QUICK_MIX_MODE_CODE:
        pool_ids = await repo.list_question_ids_all_active(
            session,
            exclude_question_ids=None,
            preferred_levels=preferred_levels,
        )
    else:
        pool_ids = await repo.list_question_ids_for_mode(
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
