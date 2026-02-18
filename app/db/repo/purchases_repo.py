from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.purchases import Purchase


class PurchasesRepo:
    @staticmethod
    async def get_by_id(session: AsyncSession, purchase_id: UUID) -> Purchase | None:
        return await session.get(Purchase, purchase_id)

    @staticmethod
    async def get_by_idempotency_key(session: AsyncSession, idempotency_key: str) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_for_credit_lock(session: AsyncSession, purchase_id: UUID) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.id == purchase_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

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
