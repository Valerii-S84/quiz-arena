from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.models.ledger_entries import LedgerEntry
from app.db.session import SessionLocal
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_ledger_entries_append_only_blocks_update_and_delete() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user("ledger-append-only")

    async with SessionLocal.begin() as session:
        entry = LedgerEntry(
            user_id=user_id,
            purchase_id=None,
            entry_type="PROMO_GRANT",
            asset="PREMIUM",
            direction="CREDIT",
            amount=7,
            balance_after=None,
            source="PROMO",
            idempotency_key="ledger-append-only:1",
            metadata_={},
            created_at=now_utc,
        )
        session.add(entry)
        await session.flush()
        entry_id = entry.id

    with pytest.raises(DBAPIError):
        async with SessionLocal.begin() as session:
            await session.execute(
                text("UPDATE ledger_entries SET amount = amount + 1 WHERE id = :entry_id"),
                {"entry_id": entry_id},
            )

    with pytest.raises(DBAPIError):
        async with SessionLocal.begin() as session:
            await session.execute(
                text("DELETE FROM ledger_entries WHERE id = :entry_id"),
                {"entry_id": entry_id},
            )


@pytest.mark.asyncio
async def test_ledger_entries_append_only_blocks_orm_mutations() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user("ledger-append-only-orm")

    async with SessionLocal.begin() as session:
        entry = LedgerEntry(
            user_id=user_id,
            purchase_id=None,
            entry_type="PROMO_GRANT",
            asset="PREMIUM",
            direction="CREDIT",
            amount=7,
            balance_after=None,
            source="PROMO",
            idempotency_key="ledger-append-only:orm",
            metadata_={},
            created_at=now_utc,
        )
        session.add(entry)
        await session.flush()
        entry_id = entry.id

    with pytest.raises(ValueError, match="append-only"):
        async with SessionLocal.begin() as session:
            entry = await session.get(LedgerEntry, entry_id)
            assert entry is not None
            entry.amount = 99
            await session.flush()

    with pytest.raises(ValueError, match="append-only"):
        async with SessionLocal.begin() as session:
            entry = await session.get(LedgerEntry, entry_id)
            assert entry is not None
            await session.delete(entry)
            await session.flush()
