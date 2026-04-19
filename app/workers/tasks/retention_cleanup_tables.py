from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repo.analytics_repo import AnalyticsRepo
from app.db.repo.outbox_events_repo import OutboxEventsRepo
from app.db.repo.processed_updates_repo import ProcessedUpdatesRepo

from .retention_cleanup_settings import clamp_retention_days

DeleteBatchFn = Callable[[AsyncSession, datetime, int], Awaitable[int]]


@dataclass(frozen=True, slots=True)
class CleanupTableSpec:
    table_name: str
    retention_days: int
    cutoff_utc: datetime
    delete_batch_fn: DeleteBatchFn


def _build_table_spec(
    *,
    table_name: str,
    retention_days: int,
    now_utc: datetime,
    delete_batch_fn: DeleteBatchFn,
) -> CleanupTableSpec:
    return CleanupTableSpec(
        table_name=table_name,
        retention_days=retention_days,
        cutoff_utc=now_utc - timedelta(days=retention_days),
        delete_batch_fn=delete_batch_fn,
    )


def build_cleanup_table_specs(
    *,
    settings: Settings,
    now_utc: datetime,
) -> tuple[CleanupTableSpec, ...]:
    return (
        _build_table_spec(
            table_name="processed_updates",
            retention_days=clamp_retention_days(settings.retention_processed_updates_days),
            now_utc=now_utc,
            delete_batch_fn=lambda session, cutoff, limit: ProcessedUpdatesRepo.delete_processed_before(
                session,
                cutoff_utc=cutoff,
                limit=limit,
            ),
        ),
        _build_table_spec(
            table_name="outbox_events",
            retention_days=clamp_retention_days(settings.retention_outbox_events_days),
            now_utc=now_utc,
            delete_batch_fn=lambda session, cutoff, limit: OutboxEventsRepo.delete_created_before(
                session,
                cutoff_utc=cutoff,
                limit=limit,
            ),
        ),
        _build_table_spec(
            table_name="analytics_events",
            retention_days=clamp_retention_days(settings.retention_analytics_events_days),
            now_utc=now_utc,
            delete_batch_fn=lambda session, cutoff, limit: AnalyticsRepo.delete_events_created_before(
                session,
                cutoff_utc=cutoff,
                limit=limit,
            ),
        ),
    )


__all__ = [
    "CleanupTableSpec",
    "DeleteBatchFn",
    "build_cleanup_table_specs",
]
