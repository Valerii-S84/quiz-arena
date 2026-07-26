from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.production_invariant_checks.delivery_daily import build_daily_cup_delivery_checks
from app.services.production_invariant_checks.delivery_telegram import (
    build_telegram_delivery_checks,
)
from app.services.production_invariant_checks.delivery_tournaments import (
    build_tournament_delivery_checks,
)
from app.services.production_invariant_checks.freshness import build_freshness_checks
from app.services.production_invariant_checks.heartbeat import build_heartbeat_checks
from app.services.production_invariant_checks.payments import build_payment_checks
from app.services.production_invariant_checks.types import (
    BLOCKING_SEVERITIES,
    STATUS_FAIL,
    InvariantCheck,
    InvariantResult,
    classify_count_result,
)
from app.workers.task_heartbeat_registry import CriticalTaskHeartbeat, get_critical_task_heartbeats


def build_invariant_checks(
    now_utc: datetime,
    *,
    heartbeat_registry: tuple[CriticalTaskHeartbeat, ...] | None = None,
) -> list[InvariantCheck]:
    registry = get_critical_task_heartbeats() if heartbeat_registry is None else heartbeat_registry
    recent_cutoff = now_utc - timedelta(days=2)
    return [
        *build_payment_checks(now_utc),
        *build_daily_cup_delivery_checks(recent_cutoff),
        *build_tournament_delivery_checks(recent_cutoff),
        *build_telegram_delivery_checks(now_utc),
        *build_freshness_checks(
            now_utc,
            now_utc.astimezone(ZoneInfo("Europe/Berlin")).date(),
        ),
        *build_heartbeat_checks(now_utc, registry),
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
