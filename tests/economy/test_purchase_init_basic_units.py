from __future__ import annotations

from datetime import datetime

import pytest

from app.db.models.purchases import Purchase
from app.economy.purchases.errors import PremiumDowngradeNotAllowedError, ProductNotFoundError
from app.economy.purchases.service import init as purchase_init
from tests.purchase_service_test_helpers import NOW, SessionStub, purchase_model


@pytest.mark.asyncio
async def test_init_purchase_creates_valid_invoice_payload_and_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Purchase] = []
    events: list[dict[str, object]] = []

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fake_get_active_invoice_for_user_product_for_update(*_args, **_kwargs):
        return None

    async def _fake_create(_session, *, purchase: Purchase, created_at: datetime):
        assert created_at == NOW
        created.append(purchase)
        return purchase

    async def _fake_emit_purchase_event(
        _session,
        *,
        event_type: str,
        purchase: Purchase,
        happened_at: datetime,
        extra_payload: dict[str, object] | None = None,
    ) -> None:
        events.append({"event_type": event_type, "purchase_id": purchase.id})
        assert happened_at == NOW
        assert extra_payload is None

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
    monkeypatch.setattr(purchase_init, "_emit_purchase_event", _fake_emit_purchase_event)

    result = await purchase_init.init_purchase(
        SessionStub(),
        user_id=7,
        product_code="ENERGY_10",
        idempotency_key="idem-new",
        now_utc=NOW,
    )

    assert result.purchase_id == created[0].id
    assert result.product_code == "ENERGY_10"
    assert result.final_stars_amount == 5
    assert result.invoice_payload.startswith("inv_")
    assert len(result.invoice_payload) == 36
    assert result.idempotent_replay is False
    assert events == [{"event_type": "purchase_init_created", "purchase_id": created[0].id}]


@pytest.mark.asyncio
async def test_init_purchase_rejects_invalid_sku() -> None:
    with pytest.raises(ProductNotFoundError):
        await purchase_init.init_purchase(
            SessionStub(),
            user_id=7,
            product_code="UNKNOWN",
            idempotency_key="idem-invalid-sku",
            now_utc=NOW,
        )


@pytest.mark.asyncio
async def test_init_purchase_replays_existing_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = purchase_model(idempotency_key="idem-existing")

    async def _fake_get_by_idempotency_key(_session, idempotency_key: str):
        assert idempotency_key == "idem-existing"
        return existing

    monkeypatch.setattr(
        purchase_init.PurchasesRepo,
        "get_by_idempotency_key",
        _fake_get_by_idempotency_key,
    )

    result = await purchase_init.init_purchase(
        SessionStub(),
        user_id=7,
        product_code="ENERGY_10",
        idempotency_key="idem-existing",
        now_utc=NOW,
    )

    assert result.purchase_id == existing.id
    assert result.invoice_payload == "inv_existing"
    assert result.idempotent_replay is True


@pytest.mark.asyncio
async def test_init_purchase_rejects_premium_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_premium = type("ActivePremium", (), {"scope": "PREMIUM_YEAR"})()

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fake_get_active_premium_for_update(_session, user_id: int, now_utc: datetime):
        assert user_id == 7
        assert now_utc == NOW
        return active_premium

    monkeypatch.setattr(
        purchase_init.PurchasesRepo,
        "get_by_idempotency_key",
        _fake_get_by_idempotency_key,
    )
    monkeypatch.setattr(
        purchase_init.EntitlementsRepo,
        "get_active_premium_for_update",
        _fake_get_active_premium_for_update,
    )

    with pytest.raises(PremiumDowngradeNotAllowedError):
        await purchase_init.init_purchase(
            SessionStub(),
            user_id=7,
            product_code="PREMIUM_MONTH",
            idempotency_key="idem-premium-downgrade",
            now_utc=NOW,
        )
