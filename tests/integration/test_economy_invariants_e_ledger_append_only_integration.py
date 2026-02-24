from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.models.ledger_entries import LedgerEntry
from app.db.session import SessionLocal
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


async def _create_ledger_entry(*, user_id: int, now_utc: datetime, suffix: str) -> int:
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
            idempotency_key=f"inv-e-ledger-append-only:{suffix}",
            metadata_={},
            created_at=now_utc,
        )
        session.add(entry)
        await session.flush()
        return entry.id


@pytest.mark.asyncio
async def test_ledger_update_fails_on_db_trigger() -> None:
    now_utc = datetime(2026, 2, 18, 17, 0, tzinfo=UTC)
    user_id = await _create_user("inv-e-ledger-update")
    entry_id = await _create_ledger_entry(user_id=user_id, now_utc=now_utc, suffix="update")

    with pytest.raises(DBAPIError) as exc_info:
        async with SessionLocal.begin() as session:
            await session.execute(
                text("UPDATE ledger_entries SET amount = amount + 1 WHERE id = :entry_id"),
                {"entry_id": entry_id},
            )

    assert "append-only" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_ledger_delete_fails_on_db_trigger() -> None:
    now_utc = datetime(2026, 2, 18, 17, 10, tzinfo=UTC)
    user_id = await _create_user("inv-e-ledger-delete")
    entry_id = await _create_ledger_entry(user_id=user_id, now_utc=now_utc, suffix="delete")

    with pytest.raises(DBAPIError) as exc_info:
        async with SessionLocal.begin() as session:
            await session.execute(
                text("DELETE FROM ledger_entries WHERE id = :entry_id"),
                {"entry_id": entry_id},
            )

    assert "append-only" in str(exc_info.value).lower()
