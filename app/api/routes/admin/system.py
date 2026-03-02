from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Awaitable, cast

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select, text

from app.api.routes.admin.deps import AdminPrincipal, add_admin_noindex_header, get_current_admin
from app.core.config import Settings, get_settings
from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.outbox_events import OutboxEvent
from app.db.models.processed_updates import ProcessedUpdate
from app.db.models.user_events import UserEvent
from app.db.session import SessionLocal
from app.services.admin.cache import get_redis_client
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/admin/system", tags=["admin-system"])


def _percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


async def _service_status(*, settings: Settings) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    status: dict[str, object] = {
        "fastapi": {"ok": True},
        "postgresql": {"ok": False},
        "redis": {"ok": False},
        "celery": {"ok": False, "workers": []},
        "bot_webhook": {"ok": False, "processed_updates_15m": 0},
    }

    async with SessionLocal.begin() as session:
        await session.execute(text("SELECT 1"))
        status["postgresql"] = {"ok": True}
        webhook_recent = int(
            (
                await session.execute(
                    select(func.count(ProcessedUpdate.update_id)).where(
                        ProcessedUpdate.processed_at >= now_utc - timedelta(minutes=15)
                    )
                )
            ).scalar_one()
            or 0
        )
        status["bot_webhook"] = {"ok": webhook_recent > 0, "processed_updates_15m": webhook_recent}

    client = await get_redis_client(settings)
    status["redis"] = {"ok": client is not None}

    try:
        inspect = celery_app.control.inspect(timeout=1.0)
        pings = inspect.ping() if inspect is not None else None
        status["celery"] = {"ok": bool(pings), "workers": list((pings or {}).keys())}
    except Exception:
        status["celery"] = {"ok": False, "workers": []}

    return status


@router.get("")
async def get_system_health(
    response: Response,
    _admin: AdminPrincipal = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    now_utc = datetime.now(timezone.utc)
    window_from = now_utc - timedelta(hours=24)

    services = await _service_status(settings=settings)

    async with SessionLocal.begin() as session:
        top_errors = (
            await session.execute(
                select(AnalyticsEvent.event_type, func.count(AnalyticsEvent.id))
                .where(
                    AnalyticsEvent.happened_at >= window_from,
                    AnalyticsEvent.event_type.ilike("%error%"),
                )
                .group_by(AnalyticsEvent.event_type)
                .order_by(func.count(AnalyticsEvent.id).desc())
                .limit(10)
            )
        ).all()

        outbox_errors = (
            await session.execute(
                select(OutboxEvent.event_type, OutboxEvent.status, OutboxEvent.created_at)
                .where(
                    OutboxEvent.created_at >= window_from,
                    OutboxEvent.status.in_(("FAILED", "ERROR")),
                )
                .order_by(OutboxEvent.created_at.desc())
                .limit(200)
            )
        ).all()

        latency_events = (
            await session.execute(
                select(UserEvent.created_at, UserEvent.payload)
                .where(
                    UserEvent.event_type == "api_latency",
                    UserEvent.created_at >= now_utc - timedelta(days=14),
                )
                .order_by(UserEvent.created_at.asc())
            )
        ).all()

    queue_stats = {"pending": 0, "failed": 0}
    client = await get_redis_client(settings)
    if client is not None:
        pending = 0
        for queue in ("q_high", "q_normal", "q_low"):
            pending += int(await cast(Awaitable[int], client.llen(queue)) or 0)
        queue_stats["pending"] = pending
        queue_stats["failed"] = int(await cast(Awaitable[int], client.llen("celery")) or 0)

    latency_map: dict[str, list[float]] = defaultdict(list)
    for created_at, payload in latency_events:
        if not isinstance(payload, dict):
            continue
        value = payload.get("latency_ms")
        if not isinstance(value, (int, float)):
            continue
        latency_map[created_at.date().isoformat()].append(float(value))

    latency_series = []
    for day_key in sorted(latency_map.keys()):
        values = latency_map[day_key]
        p50 = _percentile(values, 0.5)
        p95 = _percentile(values, 0.95)
        latency_series.append(
            {
                "date": day_key,
                "p50": round(p50, 2) if p50 is not None else None,
                "p95": round(p95, 2) if p95 is not None else None,
            }
        )

    return {
        "services": services,
        "error_log": [
            {"event_type": event_type, "status": status, "created_at": created_at.isoformat()}
            for event_type, status, created_at in outbox_errors
        ],
        "top_10_errors": [{"type": kind, "count": int(total)} for kind, total in top_errors],
        "queue_stats": queue_stats,
        "api_latency": latency_series,
    }
