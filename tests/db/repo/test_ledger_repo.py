from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.db.models.ledger_entries import LedgerEntry
from app.db.repo.ledger_repo import LedgerRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


def _ledger_entry(**overrides: object) -> LedgerEntry:
    payload: dict[str, object] = {
        "id": 10,
        "user_id": 7,
        "purchase_id": uuid4(),
        "entry_type": "PURCHASE_CREDIT",
        "asset": "PREMIUM",
        "direction": "CREDIT",
        "amount": 1,
        "balance_after": None,
        "source": "purchase",
        "idempotency_key": "ledger:test",
        "metadata_": {},
        "created_at": datetime(2026, 3, 14, 12, 0, tzinfo=UTC),
    }
    payload.update(overrides)
    return LedgerEntry(**payload)


async def test_ledger_create_lookup_and_credit_aggregates_use_expected_queries() -> None:
    entry = _ledger_entry()

    lookup_session = RecordingSession(_ScalarResult(entry))
    assert await LedgerRepo.get_by_idempotency_key(lookup_session, "ledger:test") is entry
    assert "ledger_entries.idempotency_key = 'ledger:test'" in compile_statement(
        lookup_session.statement
    )

    create_session = RecordingSession()
    assert await LedgerRepo.create(create_session, entry=entry) is entry
    assert create_session.added == [entry]
    assert create_session.flushed is True

    count_session = RecordingSession(_ScalarResult(None))
    assert await LedgerRepo.count_distinct_purchase_credits(count_session) == 0
    assert "count(DISTINCT ledger_entries.purchase_id)" in compile_statement(
        count_session.statement
    )

    stars_session = RecordingSession(_ScalarResult(900))
    assert await LedgerRepo.sum_distinct_purchase_stars_for_credits(stars_session) == 900
    stars_sql = compile_statement(stars_session.statement)
    assert "JOIN" in stars_sql
    assert "purchases.stars_amount" in stars_sql

    product_session = RecordingSession(_RowsResult([("PREMIUM_30", 300), ("ENERGY", None)]))
    assert await LedgerRepo.sum_distinct_purchase_stars_for_credits_by_product(product_session) == {
        "PREMIUM_30": 300,
        "ENERGY": 0,
    }


async def test_purchase_credit_lock_returns_single_entry_and_rejects_duplicates() -> None:
    purchase_id = uuid4()
    entry = _ledger_entry(purchase_id=purchase_id)

    missing_session = RecordingSession(_ScalarsResult([]))
    assert (
        await LedgerRepo.get_purchase_credit_for_update(
            missing_session,
            purchase_id=purchase_id,
        )
        is None
    )
    missing_sql = compile_statement(missing_session.statement)
    assert "ledger_entries.entry_type = 'PURCHASE_CREDIT'" in missing_sql
    assert "FOR UPDATE" in missing_sql

    single_session = RecordingSession(_ScalarsResult([entry]))
    assert (
        await LedgerRepo.get_purchase_credit_for_update(
            single_session,
            purchase_id=purchase_id,
        )
        is entry
    )

    duplicate_session = RecordingSession(_ScalarsResult([entry, _ledger_entry(id=11)]))
    with pytest.raises(ValueError, match="multiple purchase credit ledger entries"):
        await LedgerRepo.get_purchase_credit_for_update(
            duplicate_session,
            purchase_id=purchase_id,
        )
