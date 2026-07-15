from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.production_reliability import ProductionInvariantAlert


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
    ) -> None:
        terminal_found = await ProductionInvariantAlertsRepo._reopen_existing_terminal(
            session,
            severity=severity,
            alert_type=alert_type,
            correlation_key=correlation_key,
            seen_at=seen_at,
            safe_context=safe_context,
        )
        if terminal_found:
            return
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
                    ProductionInvariantAlert.status,
                ],
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
        await session.execute(stmt)

    @staticmethod
    async def _reopen_existing_terminal(
        session: AsyncSession,
        *,
        severity: str,
        alert_type: str,
        correlation_key: str,
        seen_at: datetime,
        safe_context: dict[str, object],
    ) -> bool:
        open_stmt = select(ProductionInvariantAlert.id).where(
            ProductionInvariantAlert.type == alert_type,
            ProductionInvariantAlert.correlation_key == correlation_key,
            ProductionInvariantAlert.status == "OPEN",
        )
        open_result = await session.execute(open_stmt)
        if open_result.scalar_one_or_none() is not None:
            return False

        terminal_stmt = (
            select(ProductionInvariantAlert.id)
            .where(
                ProductionInvariantAlert.type == alert_type,
                ProductionInvariantAlert.correlation_key == correlation_key,
                ProductionInvariantAlert.status.in_(("RESOLVED", "ACKED")),
            )
            .order_by(
                ProductionInvariantAlert.updated_at.desc(), ProductionInvariantAlert.id.desc()
            )
            .limit(1)
        )
        terminal_result = await session.execute(terminal_stmt)
        alert_id = terminal_result.scalar_one_or_none()
        if alert_id is None:
            return False

        stmt = (
            update(ProductionInvariantAlert)
            .where(
                ProductionInvariantAlert.id == alert_id,
                ProductionInvariantAlert.updated_at <= seen_at,
            )
            .values(
                severity=severity,
                status="OPEN",
                last_seen_at=seen_at,
                resolved_at=None,
                acked_at=None,
                safe_context=safe_context,
                count=ProductionInvariantAlert.count + 1,
                updated_at=seen_at,
            )
        )
        await session.execute(stmt)
        return True

    @staticmethod
    async def mark_resolved(
        session: AsyncSession,
        *,
        alert_type: str,
        correlation_key: str,
        resolved_at: datetime,
    ) -> int:
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
