from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.production_reliability_repo import ProductionInvariantAlertsRepo
from app.workers.task_heartbeat import CriticalTaskHeartbeat, get_critical_task_heartbeats

SEVERITY_P0 = "P0"
SEVERITY_P1 = "P1"
SEVERITY_P2 = "P2"
STATUS_OK = "OK"
STATUS_FAIL = "FAIL"
BLOCKING_SEVERITIES = frozenset({SEVERITY_P0, SEVERITY_P1})


@dataclass(frozen=True, slots=True)
class InvariantCheck:
    name: str
    severity: str
    sql: str
    params: dict[str, object]
    description: str
    correlation_key: str
    safe_context: dict[str, object]


@dataclass(frozen=True, slots=True)
class InvariantResult:
    name: str
    status: str
    severity: str
    count: int
    description: str
    correlation_key: str
    safe_context: dict[str, object]


def classify_count_result(check: InvariantCheck, *, count: int) -> InvariantResult:
    return InvariantResult(
        name=check.name,
        status=STATUS_OK if count == 0 else STATUS_FAIL,
        severity=check.severity,
        count=count,
        description=check.description,
        correlation_key=check.correlation_key,
        safe_context={**check.safe_context, "count": count},
    )


def build_invariant_checks(
    now_utc: datetime,
    *,
    heartbeat_registry: tuple[CriticalTaskHeartbeat, ...] | None = None,
) -> list[InvariantCheck]:
    resolved_registry = (
        get_critical_task_heartbeats() if heartbeat_registry is None else heartbeat_registry
    )
    local_today_berlin = now_utc.astimezone(ZoneInfo("Europe/Berlin")).date()
    recent_cutoff = now_utc - timedelta(days=2)
    return [
        _check(
            name="paid_without_entitlement",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM purchases p
                WHERE p.status = 'CREDITED'
                  AND p.product_type = 'PREMIUM'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM entitlements e
                    WHERE e.source_purchase_id = p.id
                      AND e.entitlement_type = 'PREMIUM'
                  )
            """,
            description="Credited premium purchase has no premium entitlement.",
        ),
        _check(
            name="paid_uncredited_age_minutes",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM purchases
                WHERE status = 'PAID_UNCREDITED'
                  AND stars_amount > 0
                  AND paid_at IS NOT NULL
                  AND paid_at <= :paid_uncredited_cutoff
            """,
            params={"paid_uncredited_cutoff": now_utc - timedelta(minutes=5)},
            description="Paid purchase remains PAID_UNCREDITED longer than 5 minutes.",
        ),
        _check(
            name="paid_without_charge_id",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM purchases
                WHERE stars_amount > 0
                  AND status IN (
                    'PAID_UNCREDITED',
                    'FAILED_CREDIT_PENDING_REVIEW',
                    'CREDITED',
                    'REFUNDED'
                  )
                  AND telegram_payment_charge_id IS NULL
            """,
            description="Paid Stars purchase is missing telegram_payment_charge_id.",
        ),
        _check(
            name="reconciliation_diff_nonzero",
            severity=SEVERITY_P1,
            sql="""
                SELECT COALESCE((
                  SELECT diff_count
                  FROM reconciliation_runs
                  WHERE finished_at IS NOT NULL
                  ORDER BY finished_at DESC, id DESC
                  LIMIT 1
                ), 0)
            """,
            description="Latest completed payment reconciliation has a non-zero diff.",
        ),
        _check(
            name="expired_active_entitlements_count",
            severity=SEVERITY_P2,
            sql="""
                SELECT count(*)
                FROM entitlements
                WHERE entitlement_type = 'PREMIUM'
                  AND status = 'ACTIVE'
                  AND ends_at IS NOT NULL
                  AND ends_at <= :now_utc
            """,
            params={"now_utc": now_utc},
            description="Expired premium entitlement rows still have ACTIVE status.",
        ),
        _check(
            name="webhook_processing_failed_or_stuck",
            severity=SEVERITY_P1,
            sql="""
                SELECT (
                  SELECT count(*)
                  FROM processed_updates
                  WHERE status = 'PROCESSING'
                    AND processed_at <= :webhook_processing_cutoff
                ) + (
                  SELECT count(*)
                  FROM outbox_events
                  WHERE event_type = 'telegram_update_failed_final'
                    AND created_at >= :recent_cutoff
                )
            """,
            params={
                "webhook_processing_cutoff": now_utc - timedelta(minutes=10),
                "recent_cutoff": now_utc - timedelta(hours=24),
            },
            description="Telegram update processing is stuck or has final failures.",
        ),
        _check(
            name="daily_cup_expected_delivery_zero_outcomes",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM tournaments t
                WHERE t.type = 'DAILY_ARENA'
                  AND t.status IN ('ROUND_1','ROUND_2','ROUND_3','ROUND_4','COMPLETED','CANCELED')
                  AND t.created_at >= :recent_cutoff
                  AND EXISTS (
                    SELECT 1
                    FROM tournament_participants p
                    WHERE p.tournament_id = t.id
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM telegram_delivery_attempts d
                    WHERE d.flow IN (
                      'daily_cup_round_messaging',
                      'daily_cup_cancel_message',
                      'daily_cup_turn_reminder'
                    )
                      AND d.correlation_id = t.id::text
                      AND d.status IN ('SENT','FAILED','SKIPPED')
                  )
            """,
            params={"recent_cutoff": recent_cutoff},
            description="Recent Daily Cup expected messaging has zero durable outcomes.",
        ),
        _check(
            name="tournament_round_expected_delivery_zero_outcomes",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM tournaments t
                WHERE t.type = 'PRIVATE'
                  AND t.status IN ('ROUND_1','ROUND_2','ROUND_3','ROUND_4','BRACKET_LIVE','COMPLETED')
                  AND t.created_at >= :recent_cutoff
                  AND EXISTS (
                    SELECT 1
                    FROM tournament_participants p
                    WHERE p.tournament_id = t.id
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM telegram_delivery_attempts d
                    WHERE d.flow = 'private_tournament_round_messaging'
                      AND d.correlation_id = t.id::text
                      AND d.status IN ('SENT','FAILED','SKIPPED')
                  )
            """,
            params={"recent_cutoff": recent_cutoff},
            description="Recent private tournament expected messaging has zero durable outcomes.",
        ),
        _check(
            name="private_tournament_round_delivery_gap",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM tournament_participants p
                JOIN tournaments t ON t.id = p.tournament_id
                WHERE t.type = 'PRIVATE'
                  AND t.status IN ('ROUND_1','ROUND_2','ROUND_3','ROUND_4','BRACKET_LIVE','COMPLETED')
                  AND t.created_at >= :recent_cutoff
                  AND NOT EXISTS (
                    SELECT 1
                    FROM telegram_delivery_attempts d
                    WHERE d.flow = 'private_tournament_round_messaging'
                      AND d.correlation_id = t.id::text
                      AND d.target_id LIKE (p.user_id::text || ':%')
                      AND d.status IN ('SENT','FAILED','SKIPPED')
                  )
            """,
            params={"recent_cutoff": recent_cutoff},
            description="Private tournament participant is missing a terminal delivery outcome.",
        ),
        _check(
            name="telegram_delivery_failure_rate",
            severity=SEVERITY_P1,
            sql="""
                WITH recent AS (
                  SELECT
                    count(*) AS total,
                    count(*) FILTER (WHERE status = 'FAILED') AS failed
                  FROM telegram_delivery_attempts
                  WHERE created_at >= :delivery_window_start
                )
                SELECT CASE
                  WHEN total >= :min_delivery_attempts
                   AND (failed * 100) >= (total * :failure_rate_percent)
                  THEN 1 ELSE 0 END
                FROM recent
            """,
            params={
                "delivery_window_start": now_utc - timedelta(hours=1),
                "min_delivery_attempts": 10,
                "failure_rate_percent": 20,
            },
            description="Telegram delivery failure rate is at least 20 percent over 1 hour.",
        ),
        _check(
            name="telegram_blocked_users_count",
            severity=SEVERITY_P2,
            sql="""
                SELECT count(DISTINCT telegram_user_id)
                FROM telegram_delivery_attempts
                WHERE is_blocked_candidate IS TRUE
                  AND telegram_user_id IS NOT NULL
            """,
            description="Telegram blocked/chat-not-found candidates require manual review.",
        ),
        _check(
            name="queue_oldest_message_age_seconds",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM outbox_events
                WHERE status IN ('NEW','PENDING','OPEN','RETRY')
                  AND created_at <= :queue_old_cutoff
            """,
            params={"queue_old_cutoff": now_utc - timedelta(minutes=15)},
            description="Outbox queue has messages older than 15 minutes.",
        ),
        _check(
            name="streak_update_stale",
            severity=SEVERITY_P1,
            sql="""
                WITH recent_activity AS (
                  SELECT max(answered_at) AS latest_answered_at
                  FROM quiz_attempts
                  WHERE answered_at >= :streak_activity_cutoff
                )
                SELECT CASE
                  WHEN (SELECT latest_answered_at FROM recent_activity) IS NULL THEN 0
                  WHEN EXISTS (
                    SELECT 1
                    FROM streak_state
                    WHERE updated_at >= (SELECT latest_answered_at FROM recent_activity)
                  ) THEN 0
                  ELSE 1
                END
            """,
            params={"streak_activity_cutoff": now_utc - timedelta(hours=6)},
            description="Quiz activity exists but streak_state has not been updated.",
        ),
        _check(
            name="global_best_streak_source_inconsistent",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM streak_state
                WHERE current_streak > best_streak
            """,
            description="Global best streak source has rows where current_streak exceeds best_streak.",
        ),
        _check(
            name="analytics_daily_stale",
            severity=SEVERITY_P2,
            sql="""
                SELECT CASE WHEN EXISTS (
                  SELECT 1
                  FROM analytics_daily
                  WHERE local_date_berlin >= :local_today_berlin
                    AND calculated_at >= :analytics_fresh_cutoff
                ) THEN 0 ELSE 1 END
            """,
            params={
                "local_today_berlin": local_today_berlin,
                "analytics_fresh_cutoff": now_utc - timedelta(hours=2),
            },
            description="Daily analytics aggregate is stale for the Berlin day.",
        ),
        _check(
            name="scheduled_offer_zero_delivery",
            severity=SEVERITY_P2,
            sql="""
                SELECT count(*)
                FROM telegram_delivery_attempts
                WHERE flow = 'scheduled_offer_delivery'
                  AND status = 'PENDING'
                  AND created_at <= :scheduled_offer_pending_cutoff
            """,
            params={"scheduled_offer_pending_cutoff": now_utc - timedelta(minutes=30)},
            description="Scheduled offer delivery attempt remains pending without a terminal outcome.",
        ),
        *_heartbeat_checks(now_utc, resolved_registry),
    ]


def read_only_sql_texts() -> list[str]:
    now_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [check.sql for check in build_invariant_checks(now_utc)]


async def run_checks_in_session(
    session: AsyncSession,
    *,
    now_utc: datetime,
    heartbeat_registry: tuple[CriticalTaskHeartbeat, ...] | None = None,
) -> list[InvariantResult]:
    results: list[InvariantResult] = []
    for check in build_invariant_checks(now_utc, heartbeat_registry=heartbeat_registry):
        db_result = await session.execute(text(check.sql), check.params)
        results.append(classify_count_result(check, count=int(db_result.scalar_one() or 0)))
    return results


async def run_database_checks(now_utc: datetime) -> list[InvariantResult]:
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        results = await run_checks_in_session(session, now_utc=now_utc)
        await session.rollback()
        return results


async def record_alerts_for_results(
    session: AsyncSession,
    *,
    results: list[InvariantResult],
    seen_at: datetime,
) -> dict[str, int]:
    opened_or_updated = 0
    resolved = 0
    for result in results:
        if result.status == STATUS_FAIL:
            await ProductionInvariantAlertsRepo.record_open(
                session,
                severity=result.severity,
                alert_type=result.name,
                correlation_key=result.correlation_key,
                seen_at=seen_at,
                safe_context=result.safe_context,
            )
            opened_or_updated += 1
            continue
        resolved += await ProductionInvariantAlertsRepo.mark_resolved(
            session,
            alert_type=result.name,
            correlation_key=result.correlation_key,
            resolved_at=seen_at,
        )
    return {"opened_or_updated": opened_or_updated, "resolved": resolved}


def exit_code_for(results: list[InvariantResult]) -> int:
    return int(
        any(
            result.status == STATUS_FAIL and result.severity in BLOCKING_SEVERITIES
            for result in results
        )
    )


def render_text(results: list[InvariantResult]) -> str:
    lines = ["production_critical_invariants:"]
    for result in results:
        lines.append(
            f"- {result.status} severity={result.severity} name={result.name} "
            f"count={result.count} description={result.description}"
        )
    return "\n".join(lines)


def render_json(results: list[InvariantResult]) -> str:
    return json.dumps([asdict(result) for result in results], indent=2, sort_keys=True)


def _check(
    *,
    name: str,
    severity: str,
    sql: str,
    description: str,
    params: dict[str, object] | None = None,
    correlation_key: str | None = None,
    safe_context: dict[str, object] | None = None,
) -> InvariantCheck:
    return InvariantCheck(
        name=name,
        severity=severity,
        sql=sql,
        params=params or {},
        description=description,
        correlation_key=correlation_key or name,
        safe_context={"check_name": name, **(safe_context or {})},
    )


def _heartbeat_checks(
    now_utc: datetime,
    heartbeat_registry: tuple[CriticalTaskHeartbeat, ...],
) -> list[InvariantCheck]:
    checks: list[InvariantCheck] = []
    for row in heartbeat_registry:
        if not row.enabled or row.stale_after_seconds is None:
            continue
        checks.append(
            _check(
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


__all__ = [
    "InvariantCheck",
    "InvariantResult",
    "build_invariant_checks",
    "classify_count_result",
    "exit_code_for",
    "read_only_sql_texts",
    "record_alerts_for_results",
    "render_json",
    "render_text",
    "run_checks_in_session",
    "run_database_checks",
]
