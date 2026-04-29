from __future__ import annotations

from datetime import datetime, timezone

from app.db.models.processed_updates import ProcessedUpdate
from app.db.repo.processed_updates_repo import ProcessedUpdatesRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult

UTC = timezone.utc


async def test_processed_update_metrics_create_status_and_age_queries() -> None:
    processed_at = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)

    create_session = RecordingSession()
    created = await ProcessedUpdatesRepo.create(
        create_session,
        update_id=1001,
        status="PROCESSING",
        processed_at=processed_at,
        processing_task_id="task-a",
    )
    assert created.update_id == 1001
    assert created.processing_task_id == "task-a"
    assert create_session.added == [created]
    assert create_session.flushed is True

    status_session = RecordingSession(_ScalarResult(1001))
    assert (
        await ProcessedUpdatesRepo.set_status(
            status_session,
            update_id=1001,
            status="DONE",
            processed_at=processed_at,
            processing_task_id=None,
        )
        == 1
    )
    status_sql = compile_statement(status_session.statement)
    assert "UPDATE processed_updates SET" in status_sql
    assert "processed_updates.update_id = 1001" in status_sql

    count_session = RecordingSession(_ScalarResult(None))
    assert (
        await ProcessedUpdatesRepo.count_processing_older_than_seconds(
            count_session,
            older_than_seconds=0,
        )
        == 0
    )
    count_sql = compile_statement(count_session.statement)
    assert "processed_updates.status = 'PROCESSING'" in count_sql
    assert ">= 1" in count_sql

    age_session = RecordingSession(_ScalarResult(-5.8))
    assert await ProcessedUpdatesRepo.get_processing_age_max_seconds(age_session) == 0


async def test_processed_update_oldest_and_slot_reclaim_queries() -> None:
    processed_at = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    row = (1001, None, processed_at, -3.7)

    oldest_session = RecordingSession(_RowsResult([row]))
    assert await ProcessedUpdatesRepo.list_oldest_processing(oldest_session, limit=0) == [
        {
            "update_id": 1001,
            "processing_task_id": None,
            "processed_at": processed_at.isoformat(),
            "age_seconds": 0,
        }
    ]
    oldest_sql = compile_statement(oldest_session.statement)
    assert "ORDER BY" in oldest_sql
    assert "LIMIT 1" in oldest_sql

    locked_update = ProcessedUpdate(
        update_id=1001,
        status="FAILED",
        processed_at=processed_at,
        processing_task_id="old-task",
    )
    lock_session = RecordingSession(_ScalarResult(locked_update))
    assert (
        await ProcessedUpdatesRepo.get_by_update_id_for_update(
            lock_session,
            update_id=1001,
        )
        is locked_update
    )
    assert "FOR UPDATE" in compile_statement(lock_session.statement)

    create_slot_session = RecordingSession(_ScalarResult(1001))
    assert (
        await ProcessedUpdatesRepo.try_create_processing_slot(
            create_slot_session,
            update_id=1001,
            processing_task_id="task-a",
        )
        is True
    )
    assert "ON CONFLICT (update_id) DO NOTHING" in compile_statement(create_slot_session.statement)

    failed_reclaim_session = RecordingSession(_ScalarResult(None))
    assert (
        await ProcessedUpdatesRepo.try_reclaim_failed_processing_slot(
            failed_reclaim_session,
            update_id=1001,
            processing_task_id="task-b",
        )
        is False
    )
    failed_sql = compile_statement(failed_reclaim_session.statement)
    assert "processed_updates.status = 'FAILED'" in failed_sql

    stale_reclaim_session = RecordingSession(_ScalarResult(1001))
    assert (
        await ProcessedUpdatesRepo.try_reclaim_stale_processing_slot(
            stale_reclaim_session,
            update_id=1001,
            processing_task_id="task-c",
            processing_ttl_seconds=0,
        )
        is True
    )
    stale_sql = compile_statement(stale_reclaim_session.statement)
    assert "processed_updates.status = 'PROCESSING'" in stale_sql
    assert ">= 1" in stale_sql
