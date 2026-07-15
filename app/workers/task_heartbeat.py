from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime, timezone
from time import monotonic
from typing import TypeVar

import structlog

from app.db.repo.production_reliability_repo import WorkerTaskHeartbeatsRepo, safe_error_hash
from app.db.session import SessionLocal
from app.workers.asyncio_runner import run_async_job
from app.workers.task_heartbeat_registry import (
    CRITICAL_TASK_HEARTBEATS,
    CriticalTaskHeartbeat,
    get_critical_task_heartbeats,
)

T = TypeVar("T")

logger = structlog.get_logger(__name__)


async def run_with_task_heartbeat(
    *,
    task_name: str,
    schedule_key: str,
    awaitable: Awaitable[T],
    session_local=SessionLocal,
) -> T:
    started_at = datetime.now(timezone.utc)
    monotonic_started = monotonic()
    await _record_started(
        task_name=task_name,
        schedule_key=schedule_key,
        started_at=started_at,
        session_local=session_local,
    )
    try:
        result = await awaitable
    except Exception as exc:
        await _record_failure(
            task_name=task_name,
            schedule_key=schedule_key,
            started_at=started_at,
            failed_at=datetime.now(timezone.utc),
            duration_ms=_duration_ms(monotonic_started),
            exc=exc,
            session_local=session_local,
        )
        raise
    await _record_success(
        task_name=task_name,
        schedule_key=schedule_key,
        started_at=started_at,
        succeeded_at=datetime.now(timezone.utc),
        duration_ms=_duration_ms(monotonic_started),
        session_local=session_local,
    )
    return result


def run_tracked_async_job(*, task_name: str, schedule_key: str, awaitable: Awaitable[T]) -> T:
    return run_async_job(
        run_with_task_heartbeat(
            task_name=task_name,
            schedule_key=schedule_key,
            awaitable=awaitable,
        )
    )


async def _record_started(*, task_name: str, schedule_key: str, started_at, session_local) -> None:
    try:
        async with session_local.begin() as session:
            await WorkerTaskHeartbeatsRepo.record_started(
                session,
                task_name=task_name,
                schedule_key=schedule_key,
                started_at=started_at,
            )
    except Exception as exc:
        logger.warning(
            "worker_task_heartbeat_start_write_failed",
            task_name=task_name,
            schedule_key=schedule_key,
            error_type=type(exc).__name__,
        )


async def _record_success(
    *,
    task_name: str,
    schedule_key: str,
    started_at,
    succeeded_at,
    duration_ms: int,
    session_local,
) -> None:
    try:
        async with session_local.begin() as session:
            await WorkerTaskHeartbeatsRepo.record_success(
                session,
                task_name=task_name,
                schedule_key=schedule_key,
                started_at=started_at,
                succeeded_at=succeeded_at,
                duration_ms=duration_ms,
            )
    except Exception as exc:
        logger.warning(
            "worker_task_heartbeat_success_write_failed",
            task_name=task_name,
            schedule_key=schedule_key,
            error_type=type(exc).__name__,
        )


async def _record_failure(
    *,
    task_name: str,
    schedule_key: str,
    started_at,
    failed_at,
    duration_ms: int,
    exc: Exception,
    session_local,
) -> None:
    try:
        async with session_local.begin() as session:
            await WorkerTaskHeartbeatsRepo.record_failure(
                session,
                task_name=task_name,
                schedule_key=schedule_key,
                started_at=started_at,
                failed_at=failed_at,
                duration_ms=duration_ms,
                error_hash=safe_error_hash(exc),
            )
    except Exception as write_exc:
        logger.warning(
            "worker_task_heartbeat_failure_write_failed",
            task_name=task_name,
            schedule_key=schedule_key,
            error_type=type(write_exc).__name__,
        )


def _duration_ms(started: float) -> int:
    return max(0, int((monotonic() - started) * 1000))


__all__ = [
    "CRITICAL_TASK_HEARTBEATS",
    "CriticalTaskHeartbeat",
    "get_critical_task_heartbeats",
    "run_tracked_async_job",
    "run_with_task_heartbeat",
]
