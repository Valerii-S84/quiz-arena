from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.purchases import Purchase


def _paid_reconciliation_filters():
    return (
        Purchase.paid_at.is_not(None),
        or_(Purchase.status != "REFUNDED", Purchase.credited_at.is_not(None)),
    )


async def count_paid_purchases(session: AsyncSession) -> int:
    stmt = select(func.count(Purchase.id)).where(*_paid_reconciliation_filters())
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def sum_paid_stars_amount(session: AsyncSession) -> int:
    stmt = select(func.coalesce(func.sum(Purchase.stars_amount), 0)).where(
        *_paid_reconciliation_filters()
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def sum_paid_stars_amount_by_product(session: AsyncSession) -> dict[str, int]:
    stmt = (
        select(
            Purchase.product_code,
            func.coalesce(func.sum(Purchase.stars_amount), 0),
        )
        .where(*_paid_reconciliation_filters())
        .group_by(Purchase.product_code)
    )
    result = await session.execute(stmt)
    return {product_code: int(total or 0) for product_code, total in result.all()}
