from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings


@dataclass(slots=True)
class _PoolCacheEntry:
    loaded_at_mono: float
    question_ids: tuple[str, ...]
    updated_at_watermark: datetime


_QUESTION_POOL_CACHE: dict[tuple[str, tuple[str, ...] | None], _PoolCacheEntry] = {}
_QUESTION_POOL_CACHE_LOCK = asyncio.Lock()


def _repo():
    from app.game.questions import runtime_bank

    return runtime_bank.QuizQuestionsRepo


def _clamp_cache_ttl_seconds(value: int) -> int:
    return max(1, min(3600, int(value)))


def clear_question_pool_cache() -> None:
    _QUESTION_POOL_CACHE.clear()


def _pool_cache_scope(mode_code: str) -> str:
    return mode_code


def _pool_matches_mode(mode_code: str, *, question_mode_code: str) -> bool:
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
) -> bool:
    return (
        question_status == "ACTIVE"
        and _pool_matches_mode(mode_code, question_mode_code=question_mode_code)
        and _pool_matches_level(preferred_levels, question_level=question_level)
    )


async def _load_pool_ids(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> tuple[str, ...]:
    pool_ids = await _repo().list_question_ids_for_mode(
        session,
        mode_code=mode_code,
        exclude_question_ids=None,
        preferred_levels=preferred_levels,
    )
    return tuple(pool_ids)


async def _build_full_pool_entry(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> _PoolCacheEntry:
    loaded_ids = await _load_pool_ids(
        session,
        mode_code=mode_code,
        preferred_levels=preferred_levels,
    )
    return _PoolCacheEntry(
        loaded_at_mono=monotonic(),
        question_ids=loaded_ids,
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

    refreshed_ids = set(cached.question_ids)
    max_updated_at = cached.updated_at_watermark
    for change in changes:
        include_question = _pool_includes_question(
            mode_code,
            preferred_levels,
            question_mode_code=change.mode_code,
            question_level=change.level,
            question_status=change.status,
        )
        if include_question:
            refreshed_ids.add(change.question_id)
        else:
            refreshed_ids.discard(change.question_id)
        if change.updated_at > max_updated_at:
            max_updated_at = change.updated_at

    return _PoolCacheEntry(
        loaded_at_mono=monotonic(),
        question_ids=tuple(sorted(refreshed_ids)),
        updated_at_watermark=max_updated_at,
    )


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
    if cached is not None and (now_mono - cached.loaded_at_mono) <= ttl_seconds:
        return cached.question_ids

    async with _QUESTION_POOL_CACHE_LOCK:
        cached = _QUESTION_POOL_CACHE.get(cache_key)
        if cached is not None and (now_mono - cached.loaded_at_mono) <= ttl_seconds:
            return cached.question_ids

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
        return updated_entry.question_ids
