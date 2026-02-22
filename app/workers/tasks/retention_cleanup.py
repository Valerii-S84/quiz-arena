from __future__ import annotations

from collections.abc import Awaitable, Callable
import asyncio
from datetime import datetime, timedelta, timezone
from random import randint
from time import perf_counter

from celery.schedules import crontab
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.repo.analytics_repo import AnalyticsRepo
from app.db.repo.outbox_events_repo import OutboxEventsRepo
from app.db.repo.processed_updates_repo import ProcessedUpdatesRepo
from app.db.session import SessionLocal
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

DeleteBatchFn = Callable[[AsyncSession, datetime, int], Awaitable[int]]


def _clamp_retention_days(value: int) -> int:
    return max(1, min(3650, int(value)))


def _clamp_batch_size(value: int) -> int:
    return max(1, min(50000, int(value)))


def _clamp_max_batches(value: int) -> int:
    return max(1, min(1000, int(value)))


def _clamp_schedule_seconds(value: int) -> int:
    return max(0, min(86400, int(value)))


def _clamp_runtime_seconds(value: int) -> int:
    return max(5, min(600, int(value)))


def _resolve_sleep_range_ms(*, minimum: int, maximum: int) -> tuple[int, int]:
    resolved_min = max(0, min(5000, int(minimum)))
    resolved_max = max(0, min(5000, int(maximum)))
    if resolved_max < resolved_min:
        return (resolved_max, resolved_min)
    return (resolved_min, resolved_max)


def _clamp_schedule_hour(value: int) -> int:
    return max(0, min(23, int(value)))


def _clamp_schedule_minute(value: int) -> int:
    return max(0, min(59, int(value)))


async def _cleanup_table_batched(
    *,
    table_name: str,
    cutoff_utc: datetime,
    retention_days: int,
    batch_size: int,
    max_batches_per_table: int,
    max_runtime_seconds: int,
    sleep_range_ms: tuple[int, int],
    delete_batch_fn: DeleteBatchFn,
) -> dict[str, object]:
    started_at = perf_counter()
    rows_deleted = 0
    batches_executed = 0
    runtime_guard_triggered = False

    for _ in range(max_batches_per_table):
        elapsed_seconds = perf_counter() - started_at
        if elapsed_seconds >= max_runtime_seconds:
            runtime_guard_triggered = True
            break
        async with SessionLocal.begin() as session:
            deleted_in_batch = await delete_batch_fn(session, cutoff_utc, batch_size)
        batches_executed += 1
        rows_deleted += deleted_in_batch
        if deleted_in_batch < batch_size:
            break
        sleep_min_ms, sleep_max_ms = sleep_range_ms
        if sleep_max_ms > 0:
            pause_ms = sleep_min_ms if sleep_min_ms == sleep_max_ms else randint(sleep_min_ms, sleep_max_ms)
            await asyncio.sleep(pause_ms / 1000)

    duration_ms = int((perf_counter() - started_at) * 1000)
    table_result: dict[str, object] = {
        "table": table_name,
        "retention_days": retention_days,
        "cutoff_utc": cutoff_utc.isoformat(),
        "rows_deleted": rows_deleted,
        "batches_executed": batches_executed,
        "duration_ms": duration_ms,
        "runtime_guard_seconds": max_runtime_seconds,
        "stopped_by_runtime_guard": runtime_guard_triggered,
        "batch_sleep_min_ms": sleep_range_ms[0],
        "batch_sleep_max_ms": sleep_range_ms[1],
        "error_count": 0,
    }
    logger.info("retention_cleanup_table_finished", **table_result)
    return table_result


async def run_retention_cleanup_async() -> dict[str, object]:
    settings = get_settings()
    now_utc = datetime.now(timezone.utc)

    processed_updates_days = _clamp_retention_days(settings.retention_processed_updates_days)
    outbox_events_days = _clamp_retention_days(settings.retention_outbox_events_days)
    analytics_events_days = _clamp_retention_days(settings.retention_analytics_events_days)
    batch_size = _clamp_batch_size(settings.retention_cleanup_batch_size)
    max_batches_per_table = _clamp_max_batches(settings.retention_cleanup_max_batches_per_table)
    max_runtime_seconds = _clamp_runtime_seconds(settings.retention_cleanup_max_runtime_seconds)
    sleep_range_ms = _resolve_sleep_range_ms(
        minimum=settings.retention_cleanup_batch_sleep_min_ms,
        maximum=settings.retention_cleanup_batch_sleep_max_ms,
    )

    table_specs: tuple[tuple[str, int, datetime, DeleteBatchFn], ...] = (
        (
            "processed_updates",
            processed_updates_days,
            now_utc - timedelta(days=processed_updates_days),
            lambda session, cutoff, limit: ProcessedUpdatesRepo.delete_processed_before(
                session,
                cutoff_utc=cutoff,
                limit=limit,
            ),
        ),
        (
            "outbox_events",
            outbox_events_days,
            now_utc - timedelta(days=outbox_events_days),
            lambda session, cutoff, limit: OutboxEventsRepo.delete_created_before(
                session,
                cutoff_utc=cutoff,
                limit=limit,
            ),
        ),
        (
            "analytics_events",
            analytics_events_days,
            now_utc - timedelta(days=analytics_events_days),
            lambda session, cutoff, limit: AnalyticsRepo.delete_events_created_before(
                session,
                cutoff_utc=cutoff,
                limit=limit,
            ),
        ),
    )

    table_results: list[dict[str, object]] = []
    total_rows_deleted = 0
    total_errors = 0

    for table_name, retention_days, cutoff_utc, delete_batch_fn in table_specs:
        table_started_at = perf_counter()
        try:
            table_result = await _cleanup_table_batched(
                table_name=table_name,
                cutoff_utc=cutoff_utc,
                retention_days=retention_days,
                batch_size=batch_size,
                max_batches_per_table=max_batches_per_table,
                max_runtime_seconds=max_runtime_seconds,
                sleep_range_ms=sleep_range_ms,
                delete_batch_fn=delete_batch_fn,
            )
        except Exception as exc:
            total_errors += 1
            table_result = {
                "table": table_name,
                "retention_days": retention_days,
                "cutoff_utc": cutoff_utc.isoformat(),
                "rows_deleted": 0,
                "batches_executed": 0,
                "duration_ms": int((perf_counter() - table_started_at) * 1000),
                "runtime_guard_seconds": max_runtime_seconds,
                "stopped_by_runtime_guard": False,
                "batch_sleep_min_ms": sleep_range_ms[0],
                "batch_sleep_max_ms": sleep_range_ms[1],
                "error_count": 1,
                "error": str(exc),
            }
            logger.exception("retention_cleanup_table_failed", **table_result)

        table_results.append(table_result)
        rows_deleted_value = table_result.get("rows_deleted", 0)
        total_rows_deleted += rows_deleted_value if isinstance(rows_deleted_value, int) else 0

    result: dict[str, object] = {
        "generated_at": now_utc.isoformat(),
        "batch_size": batch_size,
        "max_batches_per_table": max_batches_per_table,
        "max_runtime_seconds": max_runtime_seconds,
        "batch_sleep_min_ms": sleep_range_ms[0],
        "batch_sleep_max_ms": sleep_range_ms[1],
        "tables": table_results,
        "rows_deleted_total": total_rows_deleted,
        "error_count": total_errors,
    }
    if total_errors > 0:
        logger.warning("retention_cleanup_finished_with_errors", **result)
    else:
        logger.info("retention_cleanup_finished", **result)
    return result


@celery_app.task(name="app.workers.tasks.retention_cleanup.run_retention_cleanup")
def run_retention_cleanup() -> dict[str, object]:
    return run_async_job(run_retention_cleanup_async())


celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
settings = get_settings()
schedule_seconds = _clamp_schedule_seconds(settings.retention_cleanup_schedule_seconds)
schedule = (
    schedule_seconds
    if schedule_seconds > 0
    else crontab(
        hour=_clamp_schedule_hour(settings.retention_cleanup_schedule_hour_berlin),
        minute=_clamp_schedule_minute(settings.retention_cleanup_schedule_minute_berlin),
    )
)
celery_app.conf.beat_schedule.update(
    {
        "retention-cleanup-hourly": {
            "task": "app.workers.tasks.retention_cleanup.run_retention_cleanup",
            "schedule": schedule,
            "options": {"queue": "q_low"},
        },
    }
)
