from __future__ import annotations

import asyncio
import secrets

import redis.asyncio as redis

from app.core.config import Settings

OPS_UI_SESSION_KEY_PREFIX = "qa_ops_ui:session:"
_redis_client: redis.Redis | None = None
_redis_client_loop_id: int | None = None


class OpsSessionStateError(RuntimeError):
    pass


def _ops_session_key(session_id: str) -> str:
    return f"{OPS_UI_SESSION_KEY_PREFIX}{session_id}"


def _ops_session_state_unavailable() -> OpsSessionStateError:
    return OpsSessionStateError("Ops session state store is unavailable")


async def issue_ops_ui_session(*, settings: Settings, ttl_seconds: int) -> str:
    client = await _require_redis_client(settings)
    ttl = max(1, int(ttl_seconds))
    for _ in range(3):
        session_id = secrets.token_urlsafe(32)
        try:
            stored = await client.set(_ops_session_key(session_id), "1", ex=ttl, nx=True)
        except Exception as exc:
            raise _ops_session_state_unavailable() from exc
        if stored:
            return session_id
    raise OpsSessionStateError("Failed to issue a unique ops session id")


async def validate_ops_ui_session(*, settings: Settings, session_id: str | None) -> bool:
    if not session_id:
        return False
    client = await _require_redis_client(settings)
    try:
        return bool(await client.exists(_ops_session_key(session_id)))
    except Exception as exc:
        raise _ops_session_state_unavailable() from exc


async def revoke_ops_ui_session(*, settings: Settings, session_id: str | None) -> None:
    if not session_id:
        return
    client = await _require_redis_client(settings)
    try:
        await client.delete(_ops_session_key(session_id))
    except Exception as exc:
        raise _ops_session_state_unavailable() from exc


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


async def _require_redis_client(settings: Settings) -> redis.Redis:
    client = await _get_redis_client(settings)
    if client is None:
        raise _ops_session_state_unavailable()
    return client
