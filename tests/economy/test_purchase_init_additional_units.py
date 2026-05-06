from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest

from app.db.models.purchases import Purchase
from app.economy.purchases.errors import PurchaseInitValidationError
from app.economy.purchases.service import init as purchase_init
from tests.purchase_service_test_helpers import NOW, SessionStub, purchase_model
from tests.type_helpers import build_promo_redemption
@pytest.mark.asyncio
async def test_init_purchase_replays_matching_active_invoice_with_same_reserved_discount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_invoice = purchase_model(
        purchase_id=uuid4(),
        status="CREATED",
        applied_promo_code_id=22,
        discount_stars_amount=2,
        stars_amount=3,
    )
    redemption = build_promo_redemption(status="RESERVED", promo_code_id=22, user_id=7)
    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fake_validate_and_reserve_discount_redemption(
        _session, **_kwargs
    ) -> tuple[int, int]:
        return 2, 22

    async def _fake_get_active_invoice_for_user_product_for_update(*_args, **_kwargs):
        return active_invoice

    monkeypatch.setattr(
        purchase_init.PurchasesRepo, "get_by_idempotency_key", _fake_get_by_idempotency_key
    )
    monkeypatch.setattr(
        purchase_init,
        "_validate_and_reserve_discount_redemption",
        _fake_validate_and_reserve_discount_redemption,
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
        idempotency_key="idem-same-discount",
        now_utc=NOW,
        promo_redemption_id=redemption.id,
    )

    assert result.purchase_id == active_invoice.id
    assert result.idempotent_replay is True
@pytest.mark.asyncio
async def test_init_purchase_marks_stale_invoice_failed_without_expiring_missing_redemption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_invoice = purchase_model(
        purchase_id=uuid4(),
        status="CREATED",
        applied_promo_code_id=21,
    )
    created: list[Purchase] = []
    new_redemption = build_promo_redemption(status="RESERVED", promo_code_id=22, user_id=7)
    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fake_validate_and_reserve_discount_redemption(
        _session, **_kwargs
    ) -> tuple[int, int]:
        return 2, 22

    async def _fake_get_active_invoice_for_user_product_for_update(*_args, **_kwargs):
        return active_invoice

    async def _fake_get_redemption_by_applied_purchase_id_for_update(
        _session, purchase_id: UUID
    ):
        assert purchase_id == active_invoice.id
        return None

    async def _fake_get_redemption_by_id_for_update(_session, redemption_id: UUID):
        assert redemption_id == new_redemption.id
        return new_redemption

    async def _fake_create(_session, *, purchase: Purchase, created_at: datetime):
        assert created_at == NOW
        created.append(purchase)
        return purchase

    async def _fake_emit_purchase_event(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        purchase_init.PurchasesRepo, "get_by_idempotency_key", _fake_get_by_idempotency_key
    )
    monkeypatch.setattr(
        purchase_init,
        "_validate_and_reserve_discount_redemption",
        _fake_validate_and_reserve_discount_redemption,
    )
    monkeypatch.setattr(
        purchase_init.PurchasesRepo,
        "get_active_invoice_for_user_product_for_update",
        _fake_get_active_invoice_for_user_product_for_update,
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
    monkeypatch.setattr(purchase_init.PurchasesRepo, "create", _fake_create)
    monkeypatch.setattr(purchase_init, "_emit_purchase_event", _fake_emit_purchase_event)

    result = await purchase_init.init_purchase(
        SessionStub(),
        user_id=7,
        product_code="ENERGY_10",
        idempotency_key="idem-replace-stale",
        now_utc=NOW,
        promo_redemption_id=new_redemption.id,
    )

    assert active_invoice.status == "FAILED"
    assert new_redemption.applied_purchase_id == result.purchase_id == created[0].id
@pytest.mark.asyncio
async def test_init_purchase_rejects_missing_redemption_after_purchase_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None
    async def _fake_get_active_invoice_for_user_product_for_update(*_args, **_kwargs):
        return None

    async def _fake_validate_and_reserve_discount_redemption(
        _session, **_kwargs
    ) -> tuple[int, int]:
        return 2, 22

    async def _fake_create(_session, *, purchase: Purchase, created_at: datetime):
        assert created_at == NOW
        return purchase

    async def _fake_get_redemption_by_id_for_update(_session, redemption_id: UUID):
        assert isinstance(redemption_id, UUID)
        return None

    monkeypatch.setattr(
        purchase_init.PurchasesRepo, "get_by_idempotency_key", _fake_get_by_idempotency_key
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
    monkeypatch.setattr(purchase_init.PurchasesRepo, "create", _fake_create)
    monkeypatch.setattr(
        purchase_init.PromoRepo,
        "get_redemption_by_id_for_update",
        _fake_get_redemption_by_id_for_update,
    )
    with pytest.raises(PurchaseInitValidationError):
        await purchase_init.init_purchase(
            SessionStub(),
            user_id=7,
            product_code="ENERGY_10",
            idempotency_key="idem-missing-redemption",
            now_utc=NOW,
            promo_redemption_id=uuid4(),
        )
