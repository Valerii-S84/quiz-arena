from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.economy.purchases.service import refund as purchase_refund
from tests.purchase_service_test_helpers import NOW, SessionStub, refund_purchase_state


@pytest.mark.asyncio
async def test_debit_paid_energy_wallet_skips_flush_for_existing_zero_paid_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SessionStub()
    energy_state = SimpleNamespace(paid_energy=0, version=4, updated_at=None)

    async def _fake_get_by_user_id_for_update(_session, _user_id: int):
        return energy_state

    async def _fail_create_default_state(*_args, **_kwargs):
        pytest.fail("existing state should be reused")

    monkeypatch.setattr(
        purchase_refund.EnergyRepo,
        "get_by_user_id_for_update",
        _fake_get_by_user_id_for_update,
    )
    monkeypatch.setattr(
        purchase_refund.EnergyRepo,
        "create_default_state",
        _fail_create_default_state,
    )

    await purchase_refund._debit_paid_energy_wallet(
        session,
        user_id=7,
        amount=3,
        now_utc=NOW,
    )

    assert energy_state.paid_energy == 0
    assert energy_state.version == 4
    assert session.flush_calls == 0


@pytest.mark.asyncio
async def test_refund_purchase_preserves_existing_refunded_at_for_paid_uncredited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = refund_purchase_state(status="PAID_UNCREDITED")
    purchase.refunded_at = NOW - timedelta(hours=1)

    async def _fake_get_by_id_for_update(_session, _purchase_id):
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

    assert result.idempotent_replay is False
    assert purchase.status == "REFUNDED"
    assert purchase.refunded_at == NOW - timedelta(hours=1)
