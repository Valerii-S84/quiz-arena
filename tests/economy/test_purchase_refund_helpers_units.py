from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.economy.purchases.service import refund as purchase_refund
from tests.purchase_service_test_helpers import NOW, SessionStub


def test_extract_asset_breakdown_and_non_negative_int_ignore_invalid_values() -> None:
    assert purchase_refund._extract_asset_breakdown({"asset_breakdown": {"paid_energy": 3}}) == {
        "paid_energy": 3
    }
    assert purchase_refund._extract_asset_breakdown({"asset_breakdown": "invalid"}) == {}
    assert purchase_refund._extract_non_negative_int({"paid_energy": 3}, "paid_energy") == 3
    assert purchase_refund._extract_non_negative_int({"paid_energy": 0}, "paid_energy") == 0
    assert purchase_refund._extract_non_negative_int({"paid_energy": -4}, "paid_energy") == 0
    assert purchase_refund._extract_non_negative_int({"paid_energy": "4"}, "paid_energy") == 0
    assert purchase_refund._extract_non_negative_int({}, "paid_energy") == 0


@pytest.mark.asyncio
async def test_debit_paid_energy_wallet_skips_non_positive_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SessionStub()

    async def _fail_get_energy_state(_session, user_id: int):
        pytest.fail("energy state lookup should not run for a non-positive amount")

    monkeypatch.setattr(
        purchase_refund.EnergyRepo,
        "get_by_user_id_for_update",
        _fail_get_energy_state,
    )

    await purchase_refund._debit_paid_energy_wallet(
        session,
        user_id=7,
        amount=0,
        now_utc=NOW,
    )

    assert session.flush_calls == 0


@pytest.mark.asyncio
async def test_debit_paid_energy_wallet_creates_empty_state_without_negative_debit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SessionStub()
    created_state = SimpleNamespace(paid_energy=0, version=0, updated_at=None)

    async def _fake_get_energy_state(_session, _user_id: int):
        return None

    async def _fake_create_default_state(
        _session,
        *,
        user_id: int,
        now_utc,
        local_date_berlin,
        free_energy_start: int,
        free_energy_cap: int,
    ):
        assert user_id == 7
        assert now_utc == NOW
        assert local_date_berlin.isoformat() == "2026-04-28"
        assert free_energy_start >= 0
        assert free_energy_cap >= 0
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

    await purchase_refund._debit_paid_energy_wallet(
        session,
        user_id=7,
        amount=5,
        now_utc=NOW,
    )

    assert created_state.paid_energy == 0
    assert session.flush_calls == 0
