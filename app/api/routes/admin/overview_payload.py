from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin.overview_payload_sections import (
    build_overview_funnel,
    build_overview_kpis,
    load_core_snapshot,
    load_dashboard_sections,
)
from app.api.routes.admin.overview_series import fetch_alert_inputs


async def _build_alerts(
    session: AsyncSession,
    *,
    now_utc: datetime,
    quiz_to_purchase_now: float,
    quiz_to_purchase_prev: float,
) -> list[dict[str, object]]:
    webhook_errors, invalid_attempts = await fetch_alert_inputs(session, now_utc=now_utc)

    alerts: list[dict[str, object]] = []
    if webhook_errors > 0:
        alerts.append({"type": "webhook_errors", "severity": "high", "count": webhook_errors})
    if quiz_to_purchase_prev > 0 and quiz_to_purchase_now < quiz_to_purchase_prev * 0.8:
        alerts.append(
            {
                "type": "conversion_drop",
                "severity": "medium",
                "from": round(quiz_to_purchase_prev, 2),
                "to": round(quiz_to_purchase_now, 2),
            }
        )
    if invalid_attempts >= 25:
        alerts.append(
            {
                "type": "suspicious_activity",
                "severity": "medium",
                "invalid_promo_attempts_1h": invalid_attempts,
            }
        )
    return alerts


async def build_overview_payload(
    session: AsyncSession,
    *,
    now_utc: datetime,
    days: int,
) -> dict[str, object]:
    core = await load_core_snapshot(session, now_utc=now_utc, days=days)
    sections = await load_dashboard_sections(session, windows=core.windows)
    alerts = await _build_alerts(
        session,
        now_utc=now_utc,
        quiz_to_purchase_now=core.conversion_snapshot.quiz_to_purchase_now,
        quiz_to_purchase_prev=core.conversion_snapshot.quiz_to_purchase_prev,
    )
    return {
        "period": f"{days}d",
        "generated_at": now_utc,
        "kpis": build_overview_kpis(core),
        "funnel": build_overview_funnel(core),
        "alerts": alerts,
        **sections,
    }


__all__ = ["build_overview_payload"]
