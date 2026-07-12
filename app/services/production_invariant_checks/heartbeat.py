from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.production_invariant_checks.types import InvariantCheck, build_check
from app.workers.task_heartbeat import CriticalTaskHeartbeat

HEARTBEAT_CHECKER_STARTED_AT = datetime.now(timezone.utc)


def build_heartbeat_checks(
    now_utc: datetime,
    heartbeat_registry: tuple[CriticalTaskHeartbeat, ...],
    *,
    missing_heartbeat_grace_started_at: datetime | None = None,
) -> list[InvariantCheck]:
    checks: list[InvariantCheck] = []
    grace_started_at = missing_heartbeat_grace_started_at or HEARTBEAT_CHECKER_STARTED_AT
    for row in heartbeat_registry:
        if not row.enabled or row.stale_after_seconds is None:
            continue
        fresh_after = now_utc - timedelta(seconds=row.stale_after_seconds)
        missing_grace_until = grace_started_at + timedelta(seconds=row.stale_after_seconds)
        checks.append(
            build_check(
                name="worker_task_heartbeat_stale",
                severity=row.severity,
                sql="""
                    SELECT CASE
                    WHEN EXISTS (
                      SELECT 1
                      FROM worker_task_heartbeats
                      WHERE task_name = :task_name
                        AND schedule_key = :schedule_key
                        AND consecutive_failures > 0
                    ) THEN 1
                    WHEN EXISTS (
                      SELECT 1
                      FROM worker_task_heartbeats
                      WHERE task_name = :task_name
                        AND schedule_key = :schedule_key
                        AND last_success_at IS NOT NULL
                        AND last_success_at >= :fresh_after
                        AND consecutive_failures = 0
                    ) THEN 0
                    WHEN NOT EXISTS (
                      SELECT 1
                      FROM worker_task_heartbeats
                      WHERE task_name = :task_name
                        AND schedule_key = :schedule_key
                    ) AND :missing_heartbeat_grace_active THEN 0
                    ELSE 1 END
                """,
                params={
                    "task_name": row.task_name,
                    "schedule_key": row.schedule_key,
                    "fresh_after": fresh_after,
                    "missing_heartbeat_grace_active": now_utc < missing_grace_until,
                },
                description="Critical worker/beat task heartbeat is stale or failing.",
                correlation_key=f"worker_task_heartbeat_stale:{row.schedule_key}",
                safe_context={
                    "task_name": row.task_name,
                    "schedule_key": row.schedule_key,
                    "stale_after_seconds": row.stale_after_seconds,
                    "missing_heartbeat_grace_until": missing_grace_until.isoformat(),
                },
            )
        )
    return checks
