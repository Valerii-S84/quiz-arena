from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from random import randint
from time import perf_counter

import structlog

from app.core.config import Settings
from app.db.session import SessionLocal

from .retention_cleanup_settings import (
    clamp_batch_size,
    clamp_max_batches,
    clamp_runtime_seconds,
    resolve_sleep_range_ms,
)
from .retention_cleanup_tables import CleanupTableSpec, build_cleanup_table_specs

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CleanupConfig:
    batch_size: int
    max_batches_per_table: int
    max_runtime_seconds: int
    sleep_range_ms: tuple[int, int]


def build_cleanup_config(settings: Settings) -> CleanupConfig:
    return CleanupConfig(
        batch_size=clamp_batch_size(settings.retention_cleanup_batch_size),
        max_batches_per_table=clamp_max_batches(settings.retention_cleanup_max_batches_per_table),
        max_runtime_seconds=clamp_runtime_seconds(settings.retention_cleanup_max_runtime_seconds),
        sleep_range_ms=resolve_sleep_range_ms(
            minimum=settings.retention_cleanup_batch_sleep_min_ms,
            maximum=settings.retention_cleanup_batch_sleep_max_ms,
        ),
    )


async def cleanup_table_batched(
    *,
    spec: CleanupTableSpec,
    config: CleanupConfig,
) -> dict[str, object]:
    started_at = perf_counter()
    rows_deleted = 0
    batches_executed = 0
    runtime_guard_triggered = False

    for _ in range(config.max_batches_per_table):
        if perf_counter() - started_at >= config.max_runtime_seconds:
            runtime_guard_triggered = True
            break
        async with SessionLocal.begin() as session:
            deleted_in_batch = await spec.delete_batch_fn(
                session, spec.cutoff_utc, config.batch_size
            )
        batches_executed += 1
        rows_deleted += deleted_in_batch
        if deleted_in_batch < config.batch_size:
            break
        sleep_min_ms, sleep_max_ms = config.sleep_range_ms
        if sleep_max_ms > 0:
            pause_ms = (
                sleep_min_ms
                if sleep_min_ms == sleep_max_ms
                else randint(
                    sleep_min_ms,
                    sleep_max_ms,
                )
            )
            await asyncio.sleep(pause_ms / 1000)

    table_result: dict[str, object] = {
        "table": spec.table_name,
        "retention_days": spec.retention_days,
        "cutoff_utc": spec.cutoff_utc.isoformat(),
        "rows_deleted": rows_deleted,
        "batches_executed": batches_executed,
        "duration_ms": int((perf_counter() - started_at) * 1000),
        "runtime_guard_seconds": config.max_runtime_seconds,
        "stopped_by_runtime_guard": runtime_guard_triggered,
        "batch_sleep_min_ms": config.sleep_range_ms[0],
        "batch_sleep_max_ms": config.sleep_range_ms[1],
        "error_count": 0,
    }
    logger.info("retention_cleanup_table_finished", **table_result)
    return table_result


def _build_failed_table_result(
    *,
    spec: CleanupTableSpec,
    config: CleanupConfig,
    started_at: float,
    exc: Exception,
) -> dict[str, object]:
    return {
        "table": spec.table_name,
        "retention_days": spec.retention_days,
        "cutoff_utc": spec.cutoff_utc.isoformat(),
        "rows_deleted": 0,
        "batches_executed": 0,
        "duration_ms": int((perf_counter() - started_at) * 1000),
        "runtime_guard_seconds": config.max_runtime_seconds,
        "stopped_by_runtime_guard": False,
        "batch_sleep_min_ms": config.sleep_range_ms[0],
        "batch_sleep_max_ms": config.sleep_range_ms[1],
        "error_count": 1,
        "error": str(exc),
    }


async def run_cleanup_table(
    *,
    spec: CleanupTableSpec,
    config: CleanupConfig,
) -> tuple[dict[str, object], bool]:
    started_at = perf_counter()
    try:
        return await cleanup_table_batched(spec=spec, config=config), False
    except Exception as exc:
        table_result = _build_failed_table_result(
            spec=spec,
            config=config,
            started_at=started_at,
            exc=exc,
        )
        logger.exception("retention_cleanup_table_failed", **table_result)
        return table_result, True


def _rows_deleted(table_result: dict[str, object]) -> int:
    rows_deleted_value = table_result.get("rows_deleted", 0)
    return rows_deleted_value if isinstance(rows_deleted_value, int) else 0


async def run_cleanup_tables(
    *,
    specs: tuple[CleanupTableSpec, ...],
    config: CleanupConfig,
) -> tuple[list[dict[str, object]], int, int]:
    table_results: list[dict[str, object]] = []
    total_rows_deleted = 0
    total_errors = 0

    for spec in specs:
        table_result, failed = await run_cleanup_table(spec=spec, config=config)
        table_results.append(table_result)
        total_rows_deleted += _rows_deleted(table_result)
        total_errors += int(failed)
    return table_results, total_rows_deleted, total_errors


def build_cleanup_result(
    *,
    now_utc: datetime,
    config: CleanupConfig,
    table_results: list[dict[str, object]],
    total_rows_deleted: int,
    total_errors: int,
) -> dict[str, object]:
    return {
        "generated_at": now_utc.isoformat(),
        "batch_size": config.batch_size,
        "max_batches_per_table": config.max_batches_per_table,
        "max_runtime_seconds": config.max_runtime_seconds,
        "batch_sleep_min_ms": config.sleep_range_ms[0],
        "batch_sleep_max_ms": config.sleep_range_ms[1],
        "tables": table_results,
        "rows_deleted_total": total_rows_deleted,
        "error_count": total_errors,
    }


def log_cleanup_result(result: dict[str, object]) -> None:
    error_count = result.get("error_count", 0)
    if isinstance(error_count, int) and error_count > 0:
        logger.warning("retention_cleanup_finished_with_errors", **result)
        return
    logger.info("retention_cleanup_finished", **result)


__all__ = [
    "CleanupConfig",
    "CleanupTableSpec",
    "build_cleanup_config",
    "build_cleanup_result",
    "build_cleanup_table_specs",
    "cleanup_table_batched",
    "log_cleanup_result",
    "run_cleanup_table",
    "run_cleanup_tables",
]
