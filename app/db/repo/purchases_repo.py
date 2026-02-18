from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.purchases import Purchase


class PurchasesRepo:
    @staticmethod
    async def get_by_id(session: AsyncSession, purchase_id: UUID) -> Purchase | None:
        return await session.get(Purchase, purchase_id)

    @staticmethod
    async def get_by_id_for_update(session: AsyncSession, purchase_id: UUID) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.id == purchase_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_idempotency_key(session: AsyncSession, idempotency_key: str) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_invoice_payload(session: AsyncSession, invoice_payload: str) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.invoice_payload == invoice_payload)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_invoice_payload_for_update(session: AsyncSession, invoice_payload: str) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.invoice_payload == invoice_payload).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_for_credit_lock(session: AsyncSession, purchase_id: UUID) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.id == purchase_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paid_uncredited_older_than(
        session: AsyncSession,
        *,
        older_than_utc: datetime,
        limit: int = 100,
    ) -> list[Purchase]:
        stmt = (
            select(Purchase)
            .where(
                Purchase.status == "PAID_UNCREDITED",
                Purchase.paid_at.is_not(None),
                Purchase.paid_at <= older_than_utc,
            )
            .order_by(Purchase.paid_at.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_paid_purchases(session: AsyncSession) -> int:
        stmt = select(func.count(Purchase.id)).where(Purchase.paid_at.is_not(None))
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_by_user(session: AsyncSession, *, user_id: int) -> int:
        stmt = select(func.count(Purchase.id)).where(Purchase.user_id == user_id)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
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

    @staticmethod
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
