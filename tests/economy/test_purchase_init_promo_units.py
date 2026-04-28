from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest

from app.db.models.purchases import Purchase
from app.economy.purchases.service import init as purchase_init
from tests.purchase_service_test_helpers import NOW, SessionStub, purchase_model
from tests.type_helpers import build_promo_redemption


@pytest.mark.asyncio
async def test_init_purchase_replaces_active_invoice_on_reserved_discount_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_purchase_id = uuid4()
    new_redemption = build_promo_redemption(status="RESERVED", promo_code_id=22, user_id=7)
    old_redemption = build_promo_redemption(
        status="RESERVED",
        promo_code_id=21,
        user_id=7,
        applied_purchase_id=old_purchase_id,
    )
    active_invoice = purchase_model(
        purchase_id=old_purchase_id,
        status="CREATED",
        applied_promo_code_id=21,
        discount_stars_amount=1,
        stars_amount=4,
    )
    created: list[Purchase] = []

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fake_validate_and_reserve_discount_redemption(
        _session,
        *,
        redemption_id: UUID,
        user_id: int,
        product,
        now_utc: datetime,
    ) -> tuple[int, int]:
        assert redemption_id == new_redemption.id
        assert user_id == 7
        assert product.product_code == "ENERGY_10"
        assert now_utc == NOW
        return 2, 22

    async def _fake_get_active_invoice_for_user_product_for_update(*_args, **_kwargs):
        return active_invoice

    async def _fake_get_redemption_by_applied_purchase_id_for_update(
        _session,
        purchase_id: UUID,
    ):
        assert purchase_id == old_purchase_id
        return old_redemption

    async def _fake_get_redemption_by_id_for_update(_session, redemption_id: UUID):
        assert redemption_id == new_redemption.id
        return new_redemption

    async def _fake_create(_session, *, purchase: Purchase, created_at: datetime):
        assert created_at == NOW
        created.append(purchase)
        return purchase

    async def _fake_emit_purchase_event(*_args, **_kwargs) -> None:
        return None

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
    monkeypatch.setattr(
        purchase_init,
        "_validate_and_reserve_discount_redemption",
        _fake_validate_and_reserve_discount_redemption,
    )
    monkeypatch.setattr(
        purchase_init.PromoRepo,
        "get_redemption_by_applied_purchase_id_for_update",
        _fake_get_redemption_by_applied_purchase_id_for_update,
    )
    monkeypatch.setattr(
        purchase_init.PromoRepo,
        "get_redemption_by_id_for_update",
        _fake_get_redemption_by_id_for_update,
    )
    monkeypatch.setattr(purchase_init, "_emit_purchase_event", _fake_emit_purchase_event)

    result = await purchase_init.init_purchase(
        SessionStub(),
        user_id=7,
        product_code="ENERGY_10",
        idempotency_key="idem-new-discount",
        now_utc=NOW,
        promo_redemption_id=new_redemption.id,
    )

    assert active_invoice.status == "FAILED"
    assert old_redemption.status == "EXPIRED"
    assert old_redemption.reserved_until == NOW
    assert new_redemption.applied_purchase_id == result.purchase_id
    assert result.purchase_id == created[0].id
    assert result.discount_stars_amount == 2
    assert result.final_stars_amount == 3
    assert result.applied_promo_code_id == 22
