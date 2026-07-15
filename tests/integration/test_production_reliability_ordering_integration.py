from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.db.models.production_reliability import ProductionInvariantAlert, WorkerTaskHeartbeat
from app.db.repo.production_reliability_repo import (
    ProductionInvariantAlertsRepo,
    WorkerTaskHeartbeatsRepo,
)
from app.db.session import SessionLocal

BASE_TIME = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


async def test_older_heartbeat_failure_cannot_replace_newer_success() -> None:
    task_name = "integration.monotonic-heartbeat.failure-after-success"
    schedule_key = "monotonic-heartbeat-failure-after-success"
    await _clear_heartbeat(task_name, schedule_key)

    await _record_heartbeat_start(task_name, schedule_key, BASE_TIME)
    await _record_heartbeat_start(task_name, schedule_key, BASE_TIME + timedelta(minutes=1))
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

    heartbeat = await _load_heartbeat(task_name, schedule_key)
    assert heartbeat.last_success_at == BASE_TIME + timedelta(minutes=2)
    assert heartbeat.last_failed_at is None
    assert heartbeat.consecutive_failures == 0


async def test_older_heartbeat_success_cannot_clear_newer_failure() -> None:
    task_name = "integration.monotonic-heartbeat.success-after-failure"
    schedule_key = "monotonic-heartbeat-success-after-failure"
    await _clear_heartbeat(task_name, schedule_key)

    await _record_heartbeat_start(task_name, schedule_key, BASE_TIME)
    await _record_heartbeat_start(task_name, schedule_key, BASE_TIME + timedelta(minutes=1))
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

    heartbeat = await _load_heartbeat(task_name, schedule_key)
    assert heartbeat.last_success_at is None
    assert heartbeat.last_failed_at == BASE_TIME + timedelta(minutes=2)
    assert heartbeat.last_error_hash == "newer-failure"
    assert heartbeat.consecutive_failures == 1


async def test_older_invariant_pass_cannot_close_newer_failure() -> None:
    alert_type = "integration_monotonic_pass"
    correlation_key = "integration:monotonic-pass"
    await _clear_alert(alert_type, correlation_key)

    await _record_alert_failure(alert_type, correlation_key, BASE_TIME + timedelta(minutes=1))
    async with SessionLocal.begin() as session:
        resolved = await ProductionInvariantAlertsRepo.mark_resolved(
            session,
            alert_type=alert_type,
            correlation_key=correlation_key,
            resolved_at=BASE_TIME,
        )

    alert = await _load_alert(alert_type, correlation_key)
    assert resolved == 0
    assert alert.status == "OPEN"
    assert alert.updated_at == BASE_TIME + timedelta(minutes=1)


async def test_older_invariant_failure_cannot_reopen_newer_pass() -> None:
    alert_type = "integration_monotonic_failure"
    correlation_key = "integration:monotonic-failure"
    await _clear_alert(alert_type, correlation_key)

    await _record_alert_failure(alert_type, correlation_key, BASE_TIME - timedelta(minutes=1))
    async with SessionLocal.begin() as session:
        resolved = await ProductionInvariantAlertsRepo.mark_resolved(
            session,
            alert_type=alert_type,
            correlation_key=correlation_key,
            resolved_at=BASE_TIME + timedelta(minutes=1),
        )
    await _record_alert_failure(alert_type, correlation_key, BASE_TIME)

    alert = await _load_alert(alert_type, correlation_key)
    assert resolved == 1
    assert alert.status == "RESOLVED"
    assert alert.resolved_at == BASE_TIME + timedelta(minutes=1)
    assert alert.updated_at == BASE_TIME + timedelta(minutes=1)


async def _record_heartbeat_start(task_name: str, schedule_key: str, started_at: datetime) -> None:
    async with SessionLocal.begin() as session:
        await WorkerTaskHeartbeatsRepo.record_started(
            session,
            task_name=task_name,
            schedule_key=schedule_key,
            started_at=started_at,
        )


async def _record_alert_failure(alert_type: str, correlation_key: str, seen_at: datetime) -> None:
    async with SessionLocal.begin() as session:
        await ProductionInvariantAlertsRepo.record_open(
            session,
            severity="P2",
            alert_type=alert_type,
            correlation_key=correlation_key,
            seen_at=seen_at,
            safe_context={"check_name": alert_type},
        )


async def _load_heartbeat(task_name: str, schedule_key: str) -> WorkerTaskHeartbeat:
    async with SessionLocal.begin() as session:
        heartbeat = await session.scalar(
            select(WorkerTaskHeartbeat).where(
                WorkerTaskHeartbeat.task_name == task_name,
                WorkerTaskHeartbeat.schedule_key == schedule_key,
            )
        )
    assert heartbeat is not None
    return heartbeat


async def _load_alert(alert_type: str, correlation_key: str) -> ProductionInvariantAlert:
    async with SessionLocal.begin() as session:
        alert = await session.scalar(
            select(ProductionInvariantAlert).where(
                ProductionInvariantAlert.type == alert_type,
                ProductionInvariantAlert.correlation_key == correlation_key,
            )
        )
    assert alert is not None
    return alert


async def _clear_heartbeat(task_name: str, schedule_key: str) -> None:
    async with SessionLocal.begin() as session:
        await session.execute(
            delete(WorkerTaskHeartbeat).where(
                WorkerTaskHeartbeat.task_name == task_name,
                WorkerTaskHeartbeat.schedule_key == schedule_key,
            )
        )


async def _clear_alert(alert_type: str, correlation_key: str) -> None:
    async with SessionLocal.begin() as session:
        await session.execute(
            delete(ProductionInvariantAlert).where(
                ProductionInvariantAlert.type == alert_type,
                ProductionInvariantAlert.correlation_key == correlation_key,
            )
        )
