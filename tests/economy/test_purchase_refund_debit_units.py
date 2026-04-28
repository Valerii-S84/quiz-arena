from __future__ import annotations

from datetime import datetime
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
async def test_refund_purchase_debits_available_wallet_without_negative_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SessionStub()
    purchase = refund_purchase_state(status="CREDITED")
    entry = credit_entry(
        purchase_id=purchase.id,
        metadata={
            "product_code": "ENERGY_10",
            "asset_breakdown": {"paid_energy": 10, "streak_saver_tokens": 2},
        },
    )
    energy_state = SimpleNamespace(paid_energy=4, version=3, updated_at=None)
    created_entries: list[LedgerEntry] = []
    streak_debits: list[dict[str, object]] = []

    async def _fake_get_by_id_for_update(_session, _purchase_id: UUID):
        return purchase

    async def _fake_get_purchase_credit_for_update(_session, *, purchase_id: UUID):
        assert purchase_id == purchase.id
        return entry

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fake_get_energy_state_for_update(_session, _user_id: int):
        return energy_state

    async def _fake_remove_streak_saver_tokens(
        _session,
        *,
        user_id: int,
        amount: int,
        now_utc: datetime,
    ):
        streak_debits.append({"user_id": user_id, "amount": amount, "now_utc": now_utc})
        return None

    async def _fake_create_refund_entry(_session, *, entry: LedgerEntry):
        created_entries.append(entry)
        return entry

    async def _fake_revoke_active_or_scheduled_by_purchase(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(purchase_refund.LedgerRepo, "create", _fake_create_refund_entry)
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
        purchase_refund.EnergyRepo,
        "get_by_user_id_for_update",
        _fake_get_energy_state_for_update,
    )
    monkeypatch.setattr(
        purchase_refund.StreakRepo,
        "remove_streak_saver_tokens",
        _fake_remove_streak_saver_tokens,
    )
    monkeypatch.setattr(
        purchase_refund.EntitlementsRepo,
        "revoke_active_or_scheduled_by_purchase",
        _fake_revoke_active_or_scheduled_by_purchase,
    )

    result = await purchase_refund.refund_purchase(
        session,
        purchase_id=purchase.id,
        now_utc=NOW,
    )

    assert result.idempotent_replay is False
    assert purchase.status == "REFUNDED"
    assert energy_state.paid_energy == 0
    assert energy_state.version == 4
    assert session.flush_calls == 1
    assert streak_debits == [{"user_id": 7, "amount": 2, "now_utc": NOW}]
    assert created_entries[0].idempotency_key == f"refund:{purchase.id}"
    assert created_entries[0].metadata_ == {
        "product_code": "ENERGY_10",
        "asset_breakdown": {"paid_energy": 10, "streak_saver_tokens": 2},
        "source_credit_idempotency_key": entry.idempotency_key,
    }
