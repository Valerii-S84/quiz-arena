from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
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
async def test_debit_paid_energy_wallet_creates_state_and_flushes_after_positive_debit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SessionStub()
    created_state = SimpleNamespace(paid_energy=9, version=2, updated_at=None)

    async def _fake_get_energy_state(_session, _user_id: int):
        return None

    async def _fake_create_default_state(_session, **_kwargs):
        return created_state

    monkeypatch.setattr(
        purchase_refund.EnergyRepo,
        "get_by_user_id_for_update",
        _fake_get_energy_state,
    )
    monkeypatch.setattr(
        purchase_refund.EnergyRepo,
        "create_default_state",
        _fake_create_default_state,
    )

    await purchase_refund._debit_paid_energy_wallet(session, user_id=7, amount=4, now_utc=NOW)

    assert created_state.paid_energy == 5
    assert created_state.version == 3
    assert created_state.updated_at == NOW
    assert session.flush_calls == 1


@pytest.mark.asyncio
async def test_refund_purchase_preserves_existing_refunded_at_when_credit_is_reversed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="CREDITED")
    previous_refunded_at = NOW - timedelta(days=1)
    purchase.refunded_at = previous_refunded_at
    entry = credit_entry(purchase_id=purchase.id)

    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return purchase

    async def _fake_get_purchase_credit_for_update(_session, *, purchase_id: UUID):
        assert purchase_id == purchase.id
        return entry

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return object()

    async def _fake_revoke_active_or_scheduled_by_purchase(*_args, **_kwargs) -> int:
        return 0

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
        purchase_refund.LedgerRepo, "get_by_idempotency_key", _fake_get_by_idempotency_key
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
    assert purchase.refunded_at == previous_refunded_at


@pytest.mark.asyncio
async def test_refund_purchase_creates_refund_entry_with_empty_asset_breakdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="CREDITED")
    entry = credit_entry(
        purchase_id=purchase.id,
        metadata={"product_code": "ENERGY_10", "asset_breakdown": "invalid"},
    )
    created_entries: list[LedgerEntry] = []
    streak_calls: list[dict[str, object]] = []

    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return purchase

    async def _fake_get_purchase_credit_for_update(_session, *, purchase_id: UUID):
        assert purchase_id == purchase.id
        return entry

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fail_debit_paid_energy_wallet(
        _session,
        *,
        user_id: int,
        amount: int,
        now_utc: datetime,
    ):
        assert user_id == 7
        assert amount == 0
        assert now_utc == NOW
        return None

    async def _fake_remove_streak_saver_tokens(
        _session,
        *,
        user_id: int,
        amount: int,
        now_utc: datetime,
    ):
        streak_calls.append({"user_id": user_id, "amount": amount, "now_utc": now_utc})
        return None

    async def _fake_create(_session, *, entry: LedgerEntry):
        created_entries.append(entry)
        return entry

    async def _fake_revoke_active_or_scheduled_by_purchase(*_args, **_kwargs) -> int:
        return 0

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
        purchase_refund.LedgerRepo, "get_by_idempotency_key", _fake_get_by_idempotency_key
    )
    monkeypatch.setattr(
        purchase_refund,
        "_debit_paid_energy_wallet",
        _fail_debit_paid_energy_wallet,
    )
    monkeypatch.setattr(
        purchase_refund.StreakRepo, "remove_streak_saver_tokens", _fake_remove_streak_saver_tokens
    )
    monkeypatch.setattr(purchase_refund.LedgerRepo, "create", _fake_create)
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

    assert result.idempotent_replay is False
    assert streak_calls == [{"user_id": 7, "amount": 0, "now_utc": NOW}]
    assert created_entries[0].metadata_["asset_breakdown"] == {}


@pytest.mark.asyncio
async def test_refund_purchase_creates_refund_entry_and_marks_purchase_refunded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="CREDITED")
    entry = credit_entry(
        purchase_id=purchase.id,
        metadata={
            "product_code": "ENERGY_10",
            "asset_breakdown": {"paid_energy": 4, "streak_saver_tokens": 2},
        },
    )
    debits: list[dict[str, object]] = []
    streak_calls: list[dict[str, object]] = []
    created_entries: list[LedgerEntry] = []
    revoked: list[dict[str, object]] = []

    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return purchase

    async def _fake_get_purchase_credit_for_update(_session, *, purchase_id: UUID):
        assert purchase_id == purchase.id
        return entry

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fake_debit_paid_energy_wallet(
        _session,
        *,
        user_id: int,
        amount: int,
        now_utc: datetime,
    ) -> None:
        debits.append({"user_id": user_id, "amount": amount, "now_utc": now_utc})

    async def _fake_remove_streak_saver_tokens(
        _session,
        *,
        user_id: int,
        amount: int,
        now_utc: datetime,
    ) -> None:
        streak_calls.append({"user_id": user_id, "amount": amount, "now_utc": now_utc})

    async def _fake_create(_session, *, entry: LedgerEntry):
        created_entries.append(entry)
        return entry

    async def _fake_revoke_active_or_scheduled_by_purchase(
        _session,
        *,
        purchase_id: UUID,
        now_utc: datetime,
    ) -> int:
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
    monkeypatch.setattr(
        purchase_refund.LedgerRepo, "get_by_idempotency_key", _fake_get_by_idempotency_key
    )
    monkeypatch.setattr(
        purchase_refund,
        "_debit_paid_energy_wallet",
        _fake_debit_paid_energy_wallet,
    )
    monkeypatch.setattr(
        purchase_refund.StreakRepo, "remove_streak_saver_tokens", _fake_remove_streak_saver_tokens
    )
    monkeypatch.setattr(purchase_refund.LedgerRepo, "create", _fake_create)
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

    assert result.status == "REFUNDED"
    assert result.idempotent_replay is False
    assert purchase.status == "REFUNDED"
    assert purchase.refunded_at == NOW
    assert debits == [{"user_id": 7, "amount": 4, "now_utc": NOW}]
    assert streak_calls == [{"user_id": 7, "amount": 2, "now_utc": NOW}]
    assert revoked == [{"purchase_id": purchase.id, "now_utc": NOW}]
    assert created_entries[0].idempotency_key == f"refund:{purchase.id}"
    assert created_entries[0].metadata_["source_credit_idempotency_key"] == entry.idempotency_key
