from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.production_reliability import WorkerTaskHeartbeat


class WorkerTaskHeartbeatsRepo:
    @staticmethod
    async def record_started(
        session: AsyncSession,
        *,
        task_name: str,
        schedule_key: str,
        started_at: datetime,
    ) -> None:
        stmt = (
            insert(WorkerTaskHeartbeat)
            .values(
                task_name=task_name,
                schedule_key=schedule_key,
                last_started_at=started_at,
                updated_at=started_at,
            )
            .on_conflict_do_update(
                index_elements=[WorkerTaskHeartbeat.task_name, WorkerTaskHeartbeat.schedule_key],
                set_={
                    "last_started_at": started_at,
                    "updated_at": started_at,
                },
                where=_accepts_run(started_at),
            )
        )
        await session.execute(stmt)

    @staticmethod
    async def record_success(
        session: AsyncSession,
        *,
        task_name: str,
        schedule_key: str,
        started_at: datetime,
        succeeded_at: datetime,
        duration_ms: int,
    ) -> None:
        stmt = (
            insert(WorkerTaskHeartbeat)
            .values(
                task_name=task_name,
                schedule_key=schedule_key,
                last_started_at=started_at,
                last_success_at=succeeded_at,
                last_duration_ms=duration_ms,
                consecutive_failures=0,
                updated_at=succeeded_at,
            )
            .on_conflict_do_update(
                index_elements=[WorkerTaskHeartbeat.task_name, WorkerTaskHeartbeat.schedule_key],
                set_={
                    "last_started_at": started_at,
                    "last_success_at": succeeded_at,
                    "last_duration_ms": duration_ms,
                    "last_error_hash": None,
                    "consecutive_failures": 0,
                    "updated_at": succeeded_at,
                },
                where=_accepts_run(started_at),
            )
        )
        await session.execute(stmt)

    @staticmethod
    async def record_failure(
        session: AsyncSession,
        *,
        task_name: str,
        schedule_key: str,
        started_at: datetime,
        failed_at: datetime,
        duration_ms: int,
        error_hash: str,
    ) -> None:
        stmt = (
            insert(WorkerTaskHeartbeat)
            .values(
                task_name=task_name,
                schedule_key=schedule_key,
                last_started_at=started_at,
                last_failed_at=failed_at,
                last_duration_ms=duration_ms,
                last_error_hash=error_hash,
                consecutive_failures=1,
                updated_at=failed_at,
            )
            .on_conflict_do_update(
                index_elements=[WorkerTaskHeartbeat.task_name, WorkerTaskHeartbeat.schedule_key],
                set_={
                    "last_started_at": started_at,
                    "last_failed_at": failed_at,
                    "last_duration_ms": duration_ms,
                    "last_error_hash": error_hash,
                    "consecutive_failures": WorkerTaskHeartbeat.consecutive_failures + 1,
                    "updated_at": failed_at,
                },
                where=_accepts_run(started_at),
            )
        )
        await session.execute(stmt)


def _accepts_run(started_at: datetime) -> ColumnElement[bool]:
    return or_(
        WorkerTaskHeartbeat.last_started_at.is_(None),
        WorkerTaskHeartbeat.last_started_at <= started_at,
    )
