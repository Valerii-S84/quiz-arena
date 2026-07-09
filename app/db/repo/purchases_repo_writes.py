from __future__ import annotations

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.purchases import Purchase


async def expire_stale_unpaid_invoices(
    session: AsyncSession,
    *,
    older_than_utc: datetime,
) -> int:
    stmt = (
        update(Purchase)
        .where(
            Purchase.status.in_(("CREATED", "INVOICE_SENT")),
            Purchase.created_at <= older_than_utc,
            Purchase.paid_at.is_(None),
        )
        .values(status="FAILED")
    )
    result = await session.execute(stmt)
    return int(getattr(result, "rowcount", 0) or 0)


async def create(
    session: AsyncSession,
    *,
    purchase: Purchase,
    created_at: datetime,
) -> Purchase:
    purchase.created_at = created_at
    session.add(purchase)
    await session.flush()
    return purchase
