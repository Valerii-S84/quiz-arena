from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.db.models.production_reliability import WorkerTaskHeartbeat
from app.db.repo.worker_task_heartbeats_repo import WorkerTaskHeartbeatsRepo
from app.db.session import SessionLocal

BASE_TIME = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_older_failure_cannot_replace_newer_success() -> None:
    task_name = "integration.heartbeat.failure-after-success"
    schedule_key = "heartbeat-failure-after-success"
    await _clear(task_name, schedule_key)
    try:
        await _record_start(task_name, schedule_key, BASE_TIME)
        await _record_start(task_name, schedule_key, BASE_TIME + timedelta(minutes=1))
        async with SessionLocal.begin() as session:
            await WorkerTaskHeartbeatsRepo.record_success(
                session,
                task_name=task_name,
                schedule_key=schedule_key,
                started_at=BASE_TIME + timedelta(minutes=1),
                succeeded_at=BASE_TIME + timedelta(minutes=2),
                duration_ms=60_000,
            )
        async with SessionLocal.begin() as session:
            await WorkerTaskHeartbeatsRepo.record_failure(
                session,
                task_name=task_name,
                schedule_key=schedule_key,
                started_at=BASE_TIME,
                failed_at=BASE_TIME + timedelta(minutes=3),
                duration_ms=180_000,
                error_hash="older-failure",
            )

        heartbeat = await _load(task_name, schedule_key)
        assert heartbeat.last_success_at == BASE_TIME + timedelta(minutes=2)
        assert heartbeat.last_failed_at is None
        assert heartbeat.consecutive_failures == 0
    finally:
        await _clear(task_name, schedule_key)


@pytest.mark.asyncio
async def test_older_success_cannot_clear_newer_failure() -> None:
    task_name = "integration.heartbeat.success-after-failure"
    schedule_key = "heartbeat-success-after-failure"
    await _clear(task_name, schedule_key)
    try:
        await _record_start(task_name, schedule_key, BASE_TIME)
        await _record_start(task_name, schedule_key, BASE_TIME + timedelta(minutes=1))
        async with SessionLocal.begin() as session:
            await WorkerTaskHeartbeatsRepo.record_failure(
                session,
                task_name=task_name,
                schedule_key=schedule_key,
                started_at=BASE_TIME + timedelta(minutes=1),
                failed_at=BASE_TIME + timedelta(minutes=2),
                duration_ms=60_000,
                error_hash="newer-failure",
            )
        async with SessionLocal.begin() as session:
            await WorkerTaskHeartbeatsRepo.record_success(
                session,
                task_name=task_name,
                schedule_key=schedule_key,
                started_at=BASE_TIME,
                succeeded_at=BASE_TIME + timedelta(minutes=3),
                duration_ms=180_000,
            )

        heartbeat = await _load(task_name, schedule_key)
        assert heartbeat.last_success_at is None
        assert heartbeat.last_failed_at == BASE_TIME + timedelta(minutes=2)
        assert heartbeat.last_error_hash == "newer-failure"
        assert heartbeat.consecutive_failures == 1
    finally:
        await _clear(task_name, schedule_key)


async def _record_start(task_name: str, schedule_key: str, started_at: datetime) -> None:
    async with SessionLocal.begin() as session:
        await WorkerTaskHeartbeatsRepo.record_started(
            session,
            task_name=task_name,
            schedule_key=schedule_key,
            started_at=started_at,
        )


async def _load(task_name: str, schedule_key: str) -> WorkerTaskHeartbeat:
    async with SessionLocal.begin() as session:
        heartbeat = await session.scalar(
            select(WorkerTaskHeartbeat).where(
                WorkerTaskHeartbeat.task_name == task_name,
                WorkerTaskHeartbeat.schedule_key == schedule_key,
            )
        )
    assert heartbeat is not None
    return heartbeat


async def _clear(task_name: str, schedule_key: str) -> None:
    async with SessionLocal.begin() as session:
        await session.execute(
            delete(WorkerTaskHeartbeat).where(
                WorkerTaskHeartbeat.task_name == task_name,
                WorkerTaskHeartbeat.schedule_key == schedule_key,
            )
        )
