from __future__ import annotations

import asyncio

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
