from __future__ import annotations

from datetime import datetime, timezone

import structlog

from app.db.session import SessionLocal
from app.services.production_invariants import record_alerts_for_results, run_database_checks
from app.workers.celery_app import celery_app
from app.workers.task_heartbeat import run_tracked_async_job

logger = structlog.get_logger(__name__)

TASK_NAME = "app.workers.tasks.production_invariant_alerts.run_production_invariant_alerts"
SCHEDULE_KEY = "production-critical-invariant-alerts-every-5-minutes"


async def run_production_invariant_alerts_async() -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    results = await run_database_checks(now_utc)
    async with SessionLocal.begin() as session:
        alert_summary = await record_alerts_for_results(session, results=results, seen_at=now_utc)
    failed_p0_p1 = sum(
        1 for result in results if result.status == "FAIL" and result.severity in {"P0", "P1"}
    )
    failed_p2 = sum(1 for result in results if result.status == "FAIL" and result.severity == "P2")
    summary = {
        "checks_total": len(results),
        "failed_p0_p1": failed_p0_p1,
        "failed_p2": failed_p2,
        "alerts_opened_or_updated": alert_summary["opened_or_updated"],
        "alerts_resolved": alert_summary["resolved"],
    }
    if failed_p0_p1:
        logger.warning("production_invariant_alerts_detected", **summary)
    else:
        logger.info("production_invariant_alerts_ok", **summary)
    return summary


@celery_app.task(name=TASK_NAME)
def run_production_invariant_alerts() -> dict[str, int]:
    return run_tracked_async_job(
        task_name=TASK_NAME,
        schedule_key=SCHEDULE_KEY,
        awaitable=run_production_invariant_alerts_async(),
    )


celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
celery_app.conf.beat_schedule.update(
    {
        SCHEDULE_KEY: {
            "task": TASK_NAME,
            "schedule": 300.0,
            "options": {"queue": "q_normal"},
        },
    }
)


__all__ = [
    "SCHEDULE_KEY",
    "TASK_NAME",
    "run_production_invariant_alerts",
    "run_production_invariant_alerts_async",
]
