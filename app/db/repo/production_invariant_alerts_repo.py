from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.production_reliability import ProductionInvariantAlert


async def _lock_alert_lifecycle(
    session: AsyncSession,
    *,
    alert_type: str,
    correlation_key: str,
) -> None:
    lock_material = "\x1f".join((alert_type, correlation_key))
    digest = hashlib.sha256(lock_material.encode("utf-8")).digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


async def _load_latest_alert(
    session: AsyncSession,
    *,
    alert_type: str,
    correlation_key: str,
) -> ProductionInvariantAlert | None:
    result = await session.execute(
        select(ProductionInvariantAlert)
        .where(
            ProductionInvariantAlert.type == alert_type,
            ProductionInvariantAlert.correlation_key == correlation_key,
        )
        .order_by(
            ProductionInvariantAlert.updated_at.desc(),
            ProductionInvariantAlert.id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


class ProductionInvariantAlertsRepo:
    @staticmethod
    async def record_open(
        session: AsyncSession,
        *,
        severity: str,
        alert_type: str,
        correlation_key: str,
        seen_at: datetime,
        safe_context: dict[str, object],
    ) -> int:
        await _lock_alert_lifecycle(
            session,
            alert_type=alert_type,
            correlation_key=correlation_key,
        )
        latest = await _load_latest_alert(
            session,
            alert_type=alert_type,
            correlation_key=correlation_key,
        )
        if latest is not None and latest.updated_at > seen_at:
            return 0

        stmt = (
            insert(ProductionInvariantAlert)
            .values(
                severity=severity,
                type=alert_type,
                correlation_key=correlation_key,
                status="OPEN",
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                safe_context=safe_context,
                count=1,
                updated_at=seen_at,
            )
            .on_conflict_do_update(
                index_elements=[
                    ProductionInvariantAlert.type,
                    ProductionInvariantAlert.correlation_key,
                ],
                index_where=text("status = 'OPEN'"),
                set_={
                    "severity": severity,
                    "last_seen_at": seen_at,
                    "safe_context": safe_context,
                    "count": ProductionInvariantAlert.count + 1,
                    "updated_at": seen_at,
                },
                where=ProductionInvariantAlert.updated_at <= seen_at,
            )
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    async def mark_resolved(
        session: AsyncSession,
        *,
        alert_type: str,
        correlation_key: str,
        resolved_at: datetime,
    ) -> int:
        await _lock_alert_lifecycle(
            session,
            alert_type=alert_type,
            correlation_key=correlation_key,
        )
        stmt = (
            update(ProductionInvariantAlert)
            .where(
                ProductionInvariantAlert.type == alert_type,
                ProductionInvariantAlert.correlation_key == correlation_key,
                ProductionInvariantAlert.status == "OPEN",
                ProductionInvariantAlert.updated_at <= resolved_at,
            )
            .values(
                status="RESOLVED",
                last_seen_at=resolved_at,
                resolved_at=resolved_at,
                updated_at=resolved_at,
            )
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)
