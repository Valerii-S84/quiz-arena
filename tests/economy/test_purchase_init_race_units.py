from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models.purchases import Purchase
from app.economy.purchases.service import init as purchase_init
from tests.purchase_service_test_helpers import NOW, SessionStub, purchase_model


@pytest.mark.asyncio
async def test_init_purchase_reraises_repository_failure_without_active_invoice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_invoice_lookups = 0

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fake_get_active_invoice_for_user_product_for_update(*_args, **_kwargs):
        nonlocal active_invoice_lookups
        active_invoice_lookups += 1
        return None

    async def _fake_create(_session, *, purchase: Purchase, created_at: datetime):
        raise IntegrityError("insert purchases", {"id": str(purchase.id)}, Exception("duplicate"))

    monkeypatch.setattr(purchase_init.PurchasesRepo, "create", _fake_create)
    monkeypatch.setattr(
        purchase_init.PurchasesRepo,
        "get_by_idempotency_key",
        _fake_get_by_idempotency_key,
    )
    monkeypatch.setattr(
        purchase_init.PurchasesRepo,
        "get_active_invoice_for_user_product_for_update",
        _fake_get_active_invoice_for_user_product_for_update,
    )

    with pytest.raises(IntegrityError):
        await purchase_init.init_purchase(
            SessionStub(),
            user_id=7,
            product_code="ENERGY_10",
            idempotency_key="idem-create-fails",
            now_utc=NOW,
        )

    assert active_invoice_lookups == 2


@pytest.mark.asyncio
async def test_init_purchase_replays_active_invoice_after_repository_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_invoice = purchase_model(idempotency_key="idem-race-winner", invoice_payload="inv_race")
    active_invoice_results = [None, active_invoice]

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fake_get_active_invoice_for_user_product_for_update(*_args, **_kwargs):
        return active_invoice_results.pop(0)

    async def _fake_create(_session, *, purchase: Purchase, created_at: datetime):
        raise IntegrityError("insert purchases", {"id": str(purchase.id)}, Exception("race"))

    monkeypatch.setattr(purchase_init.PurchasesRepo, "create", _fake_create)
    monkeypatch.setattr(
        purchase_init.PurchasesRepo,
        "get_by_idempotency_key",
        _fake_get_by_idempotency_key,
    )
    monkeypatch.setattr(
        purchase_init.PurchasesRepo,
        "get_active_invoice_for_user_product_for_update",
        _fake_get_active_invoice_for_user_product_for_update,
    )

    result = await purchase_init.init_purchase(
        SessionStub(),
        user_id=7,
        product_code="ENERGY_10",
        idempotency_key="idem-loser",
        now_utc=NOW,
    )

    assert result.purchase_id == active_invoice.id
    assert result.invoice_payload == "inv_race"
    assert result.idempotent_replay is True
