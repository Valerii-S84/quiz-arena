from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from time import monotonic

import redis.asyncio as redis
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.repo.users_repo import UsersRepo

GLOBAL_BEST_STREAK_CACHE_KEY = "quiz_arena:global_best_streak"
_PENDING_GLOBAL_BEST_STREAK_KEY = "quiz_arena_pending_global_best_streak"

_redis_client: redis.Redis | None = None
_redis_client_loop_id: int | None = None
_local_best_streak: int | None = None
_local_best_streak_expires_at: float = 0.0
_local_lock: asyncio.Lock | None = None
_local_lock_loop_id: int | None = None


def _ttl_seconds(settings: Settings) -> int:
    return max(1, min(3600, int(settings.global_best_streak_cache_ttl_seconds)))


def _parse_cached_best(value: object) -> int | None:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return max(0, parsed)


def _get_local_best_streak() -> int | None:
    if _local_best_streak is None or monotonic() >= _local_best_streak_expires_at:
        return None
    return _local_best_streak


def _set_local_best_streak(value: int, *, ttl_seconds: int) -> None:
    global _local_best_streak, _local_best_streak_expires_at
    _local_best_streak = max(0, int(value))
    _local_best_streak_expires_at = monotonic() + max(1, int(ttl_seconds))


def _get_local_lock() -> asyncio.Lock:
    global _local_lock, _local_lock_loop_id
    current_loop_id = id(asyncio.get_running_loop())
    if _local_lock is None or _local_lock_loop_id != current_loop_id:
        _local_lock = asyncio.Lock()
        _local_lock_loop_id = current_loop_id
    return _local_lock


async def _get_redis_client(settings: Settings) -> redis.Redis | None:
    global _redis_client, _redis_client_loop_id
    current_loop_id = id(asyncio.get_running_loop())
    if _redis_client is not None and _redis_client_loop_id == current_loop_id:
        return _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None
        _redis_client_loop_id = None

    try:
        _redis_client = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        await _redis_client.ping()
    except Exception:
        _redis_client = None
        _redis_client_loop_id = None
    else:
        _redis_client_loop_id = current_loop_id
    return _redis_client


async def get_global_best_streak(session: AsyncSession) -> int:
    settings = get_settings()
    ttl_seconds = _ttl_seconds(settings)
    local_best = _get_local_best_streak()
    if local_best is not None:
        return local_best

    async with _get_local_lock():
        local_best = _get_local_best_streak()
        if local_best is not None:
            return local_best

        return await _get_global_best_streak_uncached(
            session,
            settings=settings,
            ttl_seconds=ttl_seconds,
        )


async def _get_global_best_streak_uncached(
    session: AsyncSession,
    *,
    settings: Settings,
    ttl_seconds: int,
) -> int:
    client = await _get_redis_client(settings)
    if client is not None:
        try:
            cached = _parse_cached_best(await client.get(GLOBAL_BEST_STREAK_CACHE_KEY))
        except Exception:
            cached = None
        if cached is not None:
            _set_local_best_streak(cached, ttl_seconds=ttl_seconds)
            return cached

    best_streak = await UsersRepo.get_global_best_streak(session)
    _set_local_best_streak(best_streak, ttl_seconds=ttl_seconds)
    if client is not None:
        try:
            await client.set(
                GLOBAL_BEST_STREAK_CACHE_KEY,
                str(best_streak),
                ex=ttl_seconds,
            )
        except Exception:
            pass
    return best_streak


async def maybe_update_global_best_streak(best_streak: int) -> None:
    candidate = max(0, int(best_streak))
    if candidate <= 0:
        return

    settings = get_settings()
    ttl_seconds = _ttl_seconds(settings)
    client = await _get_redis_client(settings)
    if client is None:
        local_best = _get_local_best_streak()
        if local_best is None or candidate > local_best:
            _set_local_best_streak(candidate, ttl_seconds=ttl_seconds)
        return

    script = """
local current = tonumber(redis.call('GET', KEYS[1]) or '-1')
local candidate = tonumber(ARGV[1])
if candidate > current then
  redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
  return candidate
end
return current
"""
    try:
        eval_result = client.eval(
            script,
            1,
            GLOBAL_BEST_STREAK_CACHE_KEY,
            str(candidate),
            str(ttl_seconds),
        )
        if isinstance(eval_result, Awaitable):
            eval_result = await eval_result
    except Exception:
        return

    current_best = _parse_cached_best(eval_result)
    if current_best is None:
        return
    local_best = _get_local_best_streak()
    if local_best is None or current_best > local_best:
        _set_local_best_streak(current_best, ttl_seconds=ttl_seconds)


def schedule_global_best_streak_update_after_commit(
    session: AsyncSession,
    best_streak: int,
) -> None:
    candidate = max(0, int(best_streak))
    if candidate <= 0:
        return

    loop = asyncio.get_running_loop()
    sync_session = session.sync_session
    pending = sync_session.info.get(_PENDING_GLOBAL_BEST_STREAK_KEY)
    if pending is None:
        sync_session.info[_PENDING_GLOBAL_BEST_STREAK_KEY] = candidate

        def _after_commit(committed_session) -> None:
            pending_best = committed_session.info.pop(_PENDING_GLOBAL_BEST_STREAK_KEY, None)
            if pending_best is None:
                return
            loop.create_task(maybe_update_global_best_streak(int(pending_best)))

        def _after_rollback(rolled_back_session) -> None:
            rolled_back_session.info.pop(_PENDING_GLOBAL_BEST_STREAK_KEY, None)

        event.listen(sync_session, "after_commit", _after_commit, once=True)
        event.listen(sync_session, "after_rollback", _after_rollback, once=True)
        return

    sync_session.info[_PENDING_GLOBAL_BEST_STREAK_KEY] = max(int(pending), candidate)


async def clear_global_best_streak_cache() -> None:
    global _local_best_streak, _local_best_streak_expires_at
    _local_best_streak = None
    _local_best_streak_expires_at = 0.0
    client = await _get_redis_client(get_settings())
    if client is None:
        return
    try:
        await client.delete(GLOBAL_BEST_STREAK_CACHE_KEY)
    except Exception:
        return
