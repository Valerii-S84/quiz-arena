from __future__ import annotations

from datetime import datetime, timedelta

from app.services.production_invariant_checks.types import InvariantCheck, build_check
from app.workers.task_heartbeat import CriticalTaskHeartbeat


def build_heartbeat_checks(
    now_utc: datetime,
    heartbeat_registry: tuple[CriticalTaskHeartbeat, ...],
) -> list[InvariantCheck]:
    checks: list[InvariantCheck] = []
    for row in heartbeat_registry:
        if not row.enabled or row.stale_after_seconds is None:
            continue
        checks.append(
            build_check(
                name="worker_task_heartbeat_stale",
                severity=row.severity,
                sql="""
                    SELECT CASE WHEN EXISTS (
                      SELECT 1
                      FROM worker_task_heartbeats
                      WHERE task_name = :task_name
                        AND schedule_key = :schedule_key
                        AND last_success_at IS NOT NULL
                        AND last_success_at >= :fresh_after
                        AND consecutive_failures = 0
                    ) THEN 0 ELSE 1 END
                """,
                params={
                    "task_name": row.task_name,
                    "schedule_key": row.schedule_key,
                    "fresh_after": now_utc - timedelta(seconds=row.stale_after_seconds),
                },
                description="Critical worker/beat task heartbeat is stale or failing.",
                correlation_key=f"worker_task_heartbeat_stale:{row.schedule_key}",
                safe_context={
                    "task_name": row.task_name,
                    "schedule_key": row.schedule_key,
                    "stale_after_seconds": row.stale_after_seconds,
                },
            )
        )
    return checks
