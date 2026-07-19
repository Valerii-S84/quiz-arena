from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy import cast as sa_cast
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.models.purchases import Purchase


def _paid_reconciliation_filters():
    return (
        Purchase.paid_at.is_not(None),
        or_(
            Purchase.status.in_(("PAID_UNCREDITED", "CREDITED")),
            Purchase.credited_at.is_not(None),
        ),
    )


def _paid_perk_filters():
    return (
        Purchase.paid_at.is_not(None),
        Purchase.stars_amount > 0,
        Purchase.status != "FAILED_CREDIT_PENDING_REVIEW",
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


async def count_by_user(session: AsyncSession, *, user_id: int) -> int:
    stmt = select(func.count(Purchase.id)).where(Purchase.user_id == user_id)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_paid_purchases_for_user(session: AsyncSession, *, user_id: int) -> int:
    stmt = select(func.count(Purchase.id)).where(
        Purchase.user_id == user_id,
        *_paid_perk_filters(),
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_paid_product_since(
    session: AsyncSession,
    *,
    user_id: int,
    product_code: str,
    since_utc: datetime,
) -> int:
    stmt = select(func.count(Purchase.id)).where(
        Purchase.user_id == user_id,
        Purchase.product_code == product_code,
        Purchase.paid_at >= since_utc,
        *_paid_perk_filters(),
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_credited_product(
    session: AsyncSession,
    *,
    user_id: int,
    product_code: str,
) -> int:
    stmt = select(func.count(Purchase.id)).where(
        Purchase.user_id == user_id,
        Purchase.product_code == product_code,
        Purchase.status == "CREDITED",
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_paid_uncredited_older_than(
    session: AsyncSession,
    *,
    older_than_utc: datetime,
) -> int:
    stmt = select(func.count(Purchase.id)).where(
        Purchase.status == "PAID_UNCREDITED",
        Purchase.paid_at.is_not(None),
        Purchase.paid_at <= older_than_utc,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_precheckout_ok_older_than(
    session: AsyncSession,
    *,
    older_than_utc: datetime,
) -> int:
    precheckout_event_exists = (
        select(AnalyticsEvent.id)
        .where(
            AnalyticsEvent.event_type == "purchase_precheckout_ok",
            AnalyticsEvent.payload["purchase_id"].astext == sa_cast(Purchase.id, String),
            AnalyticsEvent.happened_at <= older_than_utc,
        )
        .exists()
    )
    stmt = select(func.count(Purchase.id)).where(
        Purchase.status == "PRECHECKOUT_OK",
        Purchase.stars_amount > 0,
        precheckout_event_exists,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_credited_premium_without_entitlement(session: AsyncSession) -> int:
    entitlement_exists = (
        select(Entitlement.id)
        .where(
            Entitlement.source_purchase_id == Purchase.id,
            Entitlement.entitlement_type == "PREMIUM",
        )
        .exists()
    )
    stmt = select(func.count(Purchase.id)).where(
        Purchase.status == "CREDITED",
        Purchase.product_type == "PREMIUM",
        ~entitlement_exists,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_credited_stars_without_purchase_credit(session: AsyncSession) -> int:
    ledger_exists = (
        select(LedgerEntry.id)
        .where(
            LedgerEntry.purchase_id == Purchase.id,
            LedgerEntry.entry_type == "PURCHASE_CREDIT",
            LedgerEntry.direction == "CREDIT",
        )
        .exists()
    )
    stmt = select(func.count(Purchase.id)).where(
        Purchase.status == "CREDITED",
        Purchase.stars_amount > 0,
        ~ledger_exists,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)
