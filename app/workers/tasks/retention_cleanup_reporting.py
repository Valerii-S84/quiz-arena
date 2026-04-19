from __future__ import annotations

import structlog

from .retention_cleanup_runtime import CleanupConfig

logger = structlog.get_logger(__name__)


def build_cleanup_result(
    *,
    now_utc,
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


__all__ = ["build_cleanup_result", "log_cleanup_result"]
