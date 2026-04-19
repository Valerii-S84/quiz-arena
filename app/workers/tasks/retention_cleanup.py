from __future__ import annotations

from datetime import datetime, timezone

import structlog

from app.core.config import get_settings
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.retention_cleanup_reporting import build_cleanup_result, log_cleanup_result
from app.workers.tasks.retention_cleanup_runtime import build_cleanup_config, run_cleanup_tables
from app.workers.tasks.retention_cleanup_settings import resolve_cleanup_schedule
from app.workers.tasks.retention_cleanup_tables import build_cleanup_table_specs

logger = structlog.get_logger(__name__)


async def run_retention_cleanup_async() -> dict[str, object]:
    settings = get_settings()
    now_utc = datetime.now(timezone.utc)
    config = build_cleanup_config(settings)
    specs = build_cleanup_table_specs(settings=settings, now_utc=now_utc)
    table_results, total_rows_deleted, total_errors = await run_cleanup_tables(
        specs=specs,
        config=config,
    )
    result = build_cleanup_result(
        now_utc=now_utc,
        config=config,
        table_results=table_results,
        total_rows_deleted=total_rows_deleted,
        total_errors=total_errors,
    )
    log_cleanup_result(result)
    return result


@celery_app.task(name="app.workers.tasks.retention_cleanup.run_retention_cleanup")
def run_retention_cleanup() -> dict[str, object]:
    return run_async_job(run_retention_cleanup_async())


celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
settings = get_settings()
schedule = resolve_cleanup_schedule(settings)
celery_app.conf.beat_schedule.update(
    {
        "retention-cleanup-hourly": {
            "task": "app.workers.tasks.retention_cleanup.run_retention_cleanup",
            "schedule": schedule,
            "options": {"queue": "q_low"},
        },
    }
)
