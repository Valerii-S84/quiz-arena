from __future__ import annotations

from sqlalchemy import select
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
