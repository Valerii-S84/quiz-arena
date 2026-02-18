from __future__ import annotations

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ledger_entries import LedgerEntry


class LedgerRepo:
    @staticmethod
    async def get_by_idempotency_key(session: AsyncSession, idempotency_key: str) -> LedgerEntry | None:
        stmt = select(LedgerEntry).where(LedgerEntry.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, *, entry: LedgerEntry) -> LedgerEntry:
        session.add(entry)
        await session.flush()
        return entry

    @staticmethod
    async def count_distinct_purchase_credits(session: AsyncSession) -> int:
        stmt = select(func.count(distinct(LedgerEntry.purchase_id))).where(
            LedgerEntry.purchase_id.is_not(None),
            LedgerEntry.entry_type == "PURCHASE_CREDIT",
            LedgerEntry.direction == "CREDIT",
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)
