from __future__ import annotations

import asyncio
from typing import Any

import orjson
import redis.asyncio as redis

from app.core.config import Settings

_redis_client: redis.Redis | None = None
_redis_client_loop_id: int | None = None


async def get_redis_client(settings: Settings) -> redis.Redis | None:
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


async def get_json_cache(*, settings: Settings, key: str) -> dict[str, Any] | None:
    client = await get_redis_client(settings)
    if client is None:
        return None
    try:
        payload = await client.get(key)
    except Exception:
        return None
    if not payload:
        return None
    try:
        parsed = orjson.loads(payload)
    except orjson.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def set_json_cache(
    *, settings: Settings, key: str, value: dict[str, Any], ttl_seconds: int
) -> None:
    client = await get_redis_client(settings)
    if client is None:
        return
    try:
        await client.set(key, orjson.dumps(value).decode("utf-8"), ex=max(1, int(ttl_seconds)))
    except Exception:
        return
