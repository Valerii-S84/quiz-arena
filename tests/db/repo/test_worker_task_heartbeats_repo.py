from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects import postgresql

from app.db.models import WorkerTaskHeartbeat
from app.db.repo.worker_task_heartbeats_repo import WorkerTaskHeartbeatsRepo
from tests.db.repo._helpers import RecordingSession
from tests.type_helpers import ScalarResult

NOW_UTC = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _compiled_sql(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


async def test_started_upsert_uses_task_schedule_generation_guard() -> None:
    session = RecordingSession(ScalarResult(None))

    await WorkerTaskHeartbeatsRepo.record_started(
        session,
        task_name="task",
        schedule_key="schedule",
        started_at=NOW_UTC,
    )

    sql = _compiled_sql(session.statement)
    assert "INSERT INTO worker_task_heartbeats" in sql
    assert "ON CONFLICT (task_name, schedule_key) DO UPDATE" in sql
    assert "worker_task_heartbeats.last_started_at <= %(last_started_at_1)s" in sql


async def test_success_uses_run_start_as_generation_and_resets_failures() -> None:
    session = RecordingSession(ScalarResult(None))

    await WorkerTaskHeartbeatsRepo.record_success(
        session,
        task_name="task",
        schedule_key="schedule",
        started_at=NOW_UTC,
        succeeded_at=NOW_UTC,
        duration_ms=123,
    )

    sql = _compiled_sql(session.statement)
    assert "last_started_at" in sql
    assert "last_error_hash = %(param_" in sql
    assert "consecutive_failures = %(param_" in sql
    assert "worker_task_heartbeats.last_started_at <= %(last_started_at_1)s" in sql


async def test_failure_uses_run_start_and_increments_consecutive_failures() -> None:
    session = RecordingSession(ScalarResult(None))

    await WorkerTaskHeartbeatsRepo.record_failure(
        session,
        task_name="task",
        schedule_key="schedule",
        started_at=NOW_UTC,
        failed_at=NOW_UTC,
        duration_ms=123,
        error_hash="error-hash",
    )

    sql = _compiled_sql(session.statement)
    assert "worker_task_heartbeats.consecutive_failures + %(consecutive_failures_1)s" in sql
    assert "worker_task_heartbeats.last_started_at <= %(last_started_at_1)s" in sql


def test_worker_heartbeat_model_maps_existing_table_contract() -> None:
    assert WorkerTaskHeartbeat.__tablename__ == "worker_task_heartbeats"
    assert {column.name for column in WorkerTaskHeartbeat.__table__.columns} == {
        "id",
        "task_name",
        "schedule_key",
        "last_started_at",
        "last_success_at",
        "last_failed_at",
        "last_duration_ms",
        "last_error_hash",
        "consecutive_failures",
        "updated_at",
    }
