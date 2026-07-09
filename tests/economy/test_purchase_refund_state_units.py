from __future__ import annotations

from datetime import datetime, timedelta
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
    credited_at = NOW - timedelta(minutes=10)
    purchase.credited_at = credited_at
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
    assert purchase.credited_at == credited_at
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


@pytest.mark.asyncio
async def test_refund_purchase_marks_credit_pending_review_without_ledger_debit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="FAILED_CREDIT_PENDING_REVIEW")

    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return purchase

    async def _no_credit_entry(_session, *, purchase_id: UUID):
        assert purchase_id == purchase.id
        return None

    async def _fail_create_refund_entry(_session, *, entry: LedgerEntry):
        pytest.fail("uncredited pending-review refund should not create a refund ledger entry")

    async def _fail_revoke_entitlement(*_args, **_kwargs):
        pytest.fail("uncredited pending-review refund should not revoke entitlements")

    monkeypatch.setattr(
        purchase_refund.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )
    monkeypatch.setattr(
        purchase_refund.LedgerRepo,
        "get_purchase_credit_for_update",
        _no_credit_entry,
    )
    monkeypatch.setattr(purchase_refund.LedgerRepo, "create", _fail_create_refund_entry)
    monkeypatch.setattr(
        purchase_refund.EntitlementsRepo,
        "revoke_active_or_scheduled_by_purchase",
        _fail_revoke_entitlement,
    )

    result = await purchase_refund.refund_purchase(
        SessionStub(),
        purchase_id=purchase.id,
        now_utc=NOW,
    )

    assert result.idempotent_replay is False
    assert purchase.status == "REFUNDED"
    assert purchase.refunded_at == NOW


@pytest.mark.asyncio
async def test_refund_purchase_reverses_credit_pending_review_with_credit_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="FAILED_CREDIT_PENDING_REVIEW")
    credit = credit_entry(
        purchase_id=purchase.id,
        metadata={"product_code": "ENERGY_10", "asset_breakdown": {"paid_energy": 4}},
    )
    debits: list[dict[str, object]] = []
    refunds: list[LedgerEntry] = []
    revoked: list[dict[str, object]] = []

    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return purchase

    async def _fake_get_purchase_credit_for_update(_session, *, purchase_id: UUID):
        assert purchase_id == purchase.id
        return credit

    async def _no_existing_refund(_session, _idempotency_key: str):
        return None

    async def _fake_debit_wallet(_session, *, user_id: int, amount: int, now_utc: datetime):
        debits.append({"user_id": user_id, "amount": amount, "now_utc": now_utc})

    async def _fake_remove_streak_tokens(*_args, **_kwargs):
        return None

    async def _fake_create_refund_entry(_session, *, entry: LedgerEntry):
        refunds.append(entry)
        return entry

    async def _fake_revoke_entitlement(_session, *, purchase_id: UUID, now_utc: datetime):
        revoked.append({"purchase_id": purchase_id, "now_utc": now_utc})
        return 1

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
    monkeypatch.setattr(purchase_refund.LedgerRepo, "get_by_idempotency_key", _no_existing_refund)
    monkeypatch.setattr(purchase_refund, "_debit_paid_energy_wallet", _fake_debit_wallet)
    monkeypatch.setattr(
        purchase_refund.StreakRepo,
        "remove_streak_saver_tokens",
        _fake_remove_streak_tokens,
    )
    monkeypatch.setattr(purchase_refund.LedgerRepo, "create", _fake_create_refund_entry)
    monkeypatch.setattr(
        purchase_refund.EntitlementsRepo,
        "revoke_active_or_scheduled_by_purchase",
        _fake_revoke_entitlement,
    )

    result = await purchase_refund.refund_purchase(
        SessionStub(),
        purchase_id=purchase.id,
        now_utc=NOW,
    )

    assert result.status == "REFUNDED"
    assert purchase.status == "REFUNDED"
    assert debits == [{"user_id": 7, "amount": 4, "now_utc": NOW}]
    assert len(refunds) == 1
    assert revoked == [{"purchase_id": purchase.id, "now_utc": NOW}]
