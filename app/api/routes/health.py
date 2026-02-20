from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.workers.celery_app import celery_app

router = APIRouter(tags=["health"])


def _ok_check(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "ok"}
    if extra:
        payload.update(extra)
    return payload


def _failed_check(error: str) -> dict[str, str]:
    return {"status": "failed", "error": error}


async def _check_database() -> dict[str, Any]:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return _ok_check()
    except Exception as exc:
        return _failed_check(str(exc))


async def _check_redis() -> dict[str, Any]:
    redis_client: Redis | None = None
    try:
        redis_client = Redis.from_url(get_settings().redis_url)
        pong = await redis_client.ping()
        if pong is not True:
            return _failed_check(f"unexpected redis ping response: {pong!r}")
        return _ok_check()
    except Exception as exc:
        return _failed_check(str(exc))
    finally:
        if redis_client is not None:
            await redis_client.aclose()


def _check_celery_worker_sync() -> dict[str, Any]:
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        if inspector is None:
            return _failed_check("celery inspector is unavailable")

        replies = inspector.ping() or {}
        if not replies:
            return _failed_check("no celery workers responded to ping")

        return _ok_check({"workers": len(replies)})
    except Exception as exc:
        return _failed_check(str(exc))


async def _check_celery_worker() -> dict[str, Any]:
    return await asyncio.to_thread(_check_celery_worker_sync)


async def _collect_checks() -> dict[str, dict[str, Any]]:
    checks = await asyncio.gather(
        _check_database(),
        _check_redis(),
        _check_celery_worker(),
    )
    return {
        "database": checks[0],
        "redis": checks[1],
        "celery": checks[2],
    }


def _all_checks_ok(checks: dict[str, dict[str, Any]]) -> bool:
    return all(check.get("status") == "ok" for check in checks.values())


@router.get("/health")
async def health() -> JSONResponse:
    checks = await _collect_checks()
    is_healthy = _all_checks_ok(checks)
    return JSONResponse(
        status_code=status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ok" if is_healthy else "degraded",
            "checks": checks,
        },
    )


@router.get("/ready")
async def ready() -> JSONResponse:
    checks = await _collect_checks()
    is_ready = _all_checks_ok(checks)
    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if is_ready else "not_ready",
            "checks": checks,
        },
    )
