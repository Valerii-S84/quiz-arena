from __future__ import annotations

from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ledger_entries import LedgerEntry
from app.db.models.purchases import Purchase


class LedgerRepo:
    @staticmethod
    async def get_by_idempotency_key(
        session: AsyncSession, idempotency_key: str
    ) -> LedgerEntry | None:
        stmt = select(LedgerEntry).where(LedgerEntry.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, *, entry: LedgerEntry) -> LedgerEntry:
        session.add(entry)
        await session.flush()
        return entry

    @staticmethod
    async def get_purchase_credit_for_update(
        session: AsyncSession,
        *,
        purchase_id: UUID,
    ) -> LedgerEntry | None:
        stmt = (
            select(LedgerEntry)
            .where(
                LedgerEntry.purchase_id == purchase_id,
                LedgerEntry.entry_type == "PURCHASE_CREDIT",
                LedgerEntry.direction == "CREDIT",
            )
            .with_for_update()
        )
        result = await session.execute(stmt)
        entries = list(result.scalars().all())
        if not entries:
            return None
        if len(entries) > 1:
            raise ValueError("multiple purchase credit ledger entries found")
        return entries[0]

    @staticmethod
    async def count_distinct_purchase_credits(session: AsyncSession) -> int:
        stmt = select(func.count(distinct(LedgerEntry.purchase_id))).where(
            LedgerEntry.purchase_id.is_not(None),
            LedgerEntry.entry_type == "PURCHASE_CREDIT",
            LedgerEntry.direction == "CREDIT",
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def sum_distinct_purchase_stars_for_credits(session: AsyncSession) -> int:
        credited_purchase_ids = (
            select(distinct(LedgerEntry.purchase_id).label("purchase_id"))
            .where(
                LedgerEntry.purchase_id.is_not(None),
                LedgerEntry.entry_type == "PURCHASE_CREDIT",
                LedgerEntry.direction == "CREDIT",
            )
            .subquery()
        )

        stmt = (
            select(func.coalesce(func.sum(Purchase.stars_amount), 0))
            .select_from(Purchase)
            .join(
                credited_purchase_ids,
                Purchase.id == credited_purchase_ids.c.purchase_id,
            )
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def sum_distinct_purchase_stars_for_credits_by_product(
        session: AsyncSession,
    ) -> dict[str, int]:
        credited_purchase_ids = (
            select(distinct(LedgerEntry.purchase_id).label("purchase_id"))
            .where(
                LedgerEntry.purchase_id.is_not(None),
                LedgerEntry.entry_type == "PURCHASE_CREDIT",
                LedgerEntry.direction == "CREDIT",
            )
            .subquery()
        )

        stmt = (
            select(
                Purchase.product_code,
                func.coalesce(func.sum(Purchase.stars_amount), 0),
            )
            .select_from(Purchase)
            .join(
                credited_purchase_ids,
                Purchase.id == credited_purchase_ids.c.purchase_id,
            )
            .group_by(Purchase.product_code)
        )
        result = await session.execute(stmt)
        return {product_code: int(total or 0) for product_code, total in result.all()}
