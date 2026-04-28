from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest

from app.db.models.ledger_entries import LedgerEntry
from app.economy.purchases.service import refund as purchase_refund
from tests.purchase_service_test_helpers import (
    NOW,
    SessionStub,
    credit_entry,
    refund_purchase_state,
)


@pytest.mark.asyncio
async def test_refund_purchase_replays_already_refunded_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="REFUNDED")
    purchase.refunded_at = NOW

    async def _fake_get_by_id_for_update(_session, purchase_id: UUID):
        assert purchase_id == purchase.id
        return purchase

    monkeypatch.setattr(
        purchase_refund.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )

    result = await purchase_refund.refund_purchase(
        SessionStub(),
        purchase_id=purchase.id,
        now_utc=NOW,
    )

    assert result.status == "REFUNDED"
    assert result.idempotent_replay is True
    assert purchase.refunded_at == NOW


@pytest.mark.asyncio
async def test_refund_purchase_reuses_existing_refund_entry_without_duplicate_debit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="CREDITED")
    existing_refund_entry = object()
    revoked: list[dict[str, object]] = []

    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return purchase

    async def _fake_get_purchase_credit_for_update(_session, *, purchase_id: UUID):
        return credit_entry(purchase_id=purchase_id)

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return existing_refund_entry

    async def _fail_create_refund_entry(_session, *, entry: LedgerEntry):
        pytest.fail("refund ledger entry should not be duplicated")

    async def _fake_revoke_active_or_scheduled_by_purchase(
        _session,
        *,
        purchase_id: UUID,
        now_utc: datetime,
    ) -> int:
        revoked.append({"purchase_id": purchase_id, "now_utc": now_utc})
        return 1

    monkeypatch.setattr(purchase_refund.LedgerRepo, "create", _fail_create_refund_entry)
    monkeypatch.setattr(
        purchase_refund.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )
    monkeypatch.setattr(
        purchase_refund.LedgerRepo,
        "get_purchase_credit_for_update",
        _fake_get_purchase_credit_for_update,
    )
    monkeypatch.setattr(
        purchase_refund.LedgerRepo,
        "get_by_idempotency_key",
        _fake_get_by_idempotency_key,
    )
    monkeypatch.setattr(
        purchase_refund.EntitlementsRepo,
        "revoke_active_or_scheduled_by_purchase",
        _fake_revoke_active_or_scheduled_by_purchase,
    )

    result = await purchase_refund.refund_purchase(
        SessionStub(),
        purchase_id=purchase.id,
        now_utc=NOW,
    )

    assert result.idempotent_replay is True
    assert purchase.status == "REFUNDED"
    assert revoked == [{"purchase_id": purchase.id, "now_utc": NOW}]


@pytest.mark.asyncio
async def test_refund_purchase_marks_paid_uncredited_without_ledger_debit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="PAID_UNCREDITED")

    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return purchase

    async def _fail_get_purchase_credit_for_update(_session, *, purchase_id: UUID):
        pytest.fail("paid-uncredited refund should not require a credit ledger entry")

    monkeypatch.setattr(
        purchase_refund.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )
    monkeypatch.setattr(
        purchase_refund.LedgerRepo,
        "get_purchase_credit_for_update",
        _fail_get_purchase_credit_for_update,
    )

    result = await purchase_refund.refund_purchase(
        SessionStub(),
        purchase_id=purchase.id,
        now_utc=NOW,
    )

    assert result.idempotent_replay is False
    assert purchase.status == "REFUNDED"
    assert purchase.refunded_at == NOW
