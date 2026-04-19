from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.processed_updates import ProcessedUpdate
from app.db.repo.processed_updates_repo import ProcessedUpdatesRepo
from app.db.session import SessionLocal


@pytest.mark.asyncio
async def test_try_create_processing_slot_rejects_duplicate_insert() -> None:
    async with SessionLocal.begin() as session:
        created = await ProcessedUpdatesRepo.try_create_processing_slot(
            session,
            update_id=123_456,
            processing_task_id="task-1",
        )

    async with SessionLocal.begin() as session:
        duplicate = await ProcessedUpdatesRepo.try_create_processing_slot(
            session,
            update_id=123_456,
            processing_task_id="task-2",
        )

    async with SessionLocal.begin() as session:
        row = await session.get(ProcessedUpdate, 123_456)

    assert created is True
    assert duplicate is False
    assert row is not None
    assert row.status == "PROCESSING"
    assert row.processing_task_id == "task-1"


@pytest.mark.asyncio
async def test_try_create_processing_slot_is_atomic_under_race_condition() -> None:
    async def _acquire_slot(task_id: str) -> bool:
        async with SessionLocal.begin() as session:
            return await ProcessedUpdatesRepo.try_create_processing_slot(
                session,
                update_id=654_321,
                processing_task_id=task_id,
            )

    first, second = await asyncio.gather(
        _acquire_slot("task-1"),
        _acquire_slot("task-2"),
    )

    async with SessionLocal.begin() as session:
        row = await session.get(ProcessedUpdate, 654_321)

    assert sorted([first, second]) == [False, True]
    assert row is not None
    assert row.status == "PROCESSING"
    assert row.processing_task_id in {"task-1", "task-2"}


@pytest.mark.asyncio
async def test_processing_observability_queries_ignore_non_processing_rows() -> None:
    now_utc = datetime.now(timezone.utc)

    async with SessionLocal.begin() as session:
        await ProcessedUpdatesRepo.create(
            session,
            update_id=800_001,
            status="PROCESSING",
            processed_at=now_utc - timedelta(hours=2),
            processing_task_id="task-oldest",
        )
        await ProcessedUpdatesRepo.create(
            session,
            update_id=800_002,
            status="PROCESSING",
            processed_at=now_utc - timedelta(minutes=10),
            processing_task_id="task-newer",
        )
        await ProcessedUpdatesRepo.create(
            session,
            update_id=800_003,
            status="DONE",
            processed_at=now_utc - timedelta(hours=3),
            processing_task_id="task-done",
        )

    async with SessionLocal.begin() as session:
        older_count = await ProcessedUpdatesRepo.count_processing_older_than_seconds(
            session,
            older_than_seconds=3_600,
        )
        max_age_seconds = await ProcessedUpdatesRepo.get_processing_age_max_seconds(session)
        oldest_processing = await ProcessedUpdatesRepo.list_oldest_processing(session, limit=2)

    assert older_count == 1
    assert max_age_seconds >= 7_000
    assert [item["update_id"] for item in oldest_processing] == [800_001, 800_002]
    assert all(item["processing_task_id"] is not None for item in oldest_processing)
