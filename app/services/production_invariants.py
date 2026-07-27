from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.production_invariant_alerts_repo import ProductionInvariantAlertsRepo
from app.services.production_invariant_checks.runner import (
    build_invariant_checks,
    exit_code_for,
    read_only_sql_texts,
    render_json,
    render_text,
    run_checks_in_session,
    run_database_checks,
)
from app.services.production_invariant_checks.types import (
    STATUS_FAIL,
    InvariantCheck,
    InvariantResult,
    classify_count_result,
)


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
            opened_or_updated += await ProductionInvariantAlertsRepo.record_open(
                session,
                severity=result.severity,
                alert_type=result.name,
                correlation_key=result.correlation_key,
                seen_at=seen_at,
                safe_context=result.safe_context,
            )
            continue
        resolved += await ProductionInvariantAlertsRepo.mark_resolved(
            session,
            alert_type=result.name,
            correlation_key=result.correlation_key,
            resolved_at=seen_at,
        )
    return {"opened_or_updated": opened_or_updated, "resolved": resolved}


__all__ = [
    "InvariantCheck",
    "InvariantResult",
    "ProductionInvariantAlertsRepo",
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
