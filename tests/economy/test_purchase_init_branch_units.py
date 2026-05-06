from __future__ import annotations

from datetime import datetime

import pytest

from app.db.models.purchases import Purchase
from app.economy.purchases.service import init as purchase_init
from tests.purchase_service_test_helpers import NOW, SessionStub, purchase_model


@pytest.mark.asyncio
async def test_init_purchase_checks_streak_saver_limit_for_streak_saver_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Purchase] = []
    streak_checks: list[dict[str, object]] = []

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fake_validate_streak_saver_purchase_limit(_session, *, user_id: int, now_utc):
        streak_checks.append({"user_id": user_id, "now_utc": now_utc})

    async def _fake_get_active_invoice_for_user_product_for_update(*_args, **_kwargs):
        return None

    async def _fake_create(_session, *, purchase: Purchase, created_at: datetime):
        assert created_at == NOW
        created.append(purchase)
        return purchase

    async def _fake_emit_purchase_event(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        purchase_init.PurchasesRepo,
        "get_by_idempotency_key",
        _fake_get_by_idempotency_key,
    )
    monkeypatch.setattr(
        purchase_init,
        "_validate_streak_saver_purchase_limit",
        _fake_validate_streak_saver_purchase_limit,
    )
    monkeypatch.setattr(
        purchase_init.PurchasesRepo,
        "get_active_invoice_for_user_product_for_update",
        _fake_get_active_invoice_for_user_product_for_update,
    )
    monkeypatch.setattr(purchase_init.PurchasesRepo, "create", _fake_create)
    monkeypatch.setattr(purchase_init, "_emit_purchase_event", _fake_emit_purchase_event)

    result = await purchase_init.init_purchase(
        SessionStub(),
        user_id=7,
        product_code="STREAK_SAVER_20",
        idempotency_key="idem-streak-saver",
        now_utc=NOW,
    )

    assert result.product_code == "STREAK_SAVER_20"
    assert created[0].product_code == "STREAK_SAVER_20"
    assert streak_checks == [{"user_id": 7, "now_utc": NOW}]


@pytest.mark.asyncio
async def test_init_purchase_allows_upgrade_to_higher_premium_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Purchase] = []
    active_premium = type("ActivePremium", (), {"scope": "PREMIUM_WEEK"})()

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fake_get_active_premium_for_update(_session, user_id: int, now_utc):
        assert user_id == 7
        assert now_utc == NOW
        return active_premium

    async def _fake_get_active_invoice_for_user_product_for_update(*_args, **_kwargs):
        return None

    async def _fake_create(_session, *, purchase: Purchase, created_at: datetime):
        assert created_at == NOW
        created.append(purchase)
        return purchase

    async def _fake_emit_purchase_event(*_args, **_kwargs) -> None:
        return None

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
    monkeypatch.setattr(
        purchase_init.PurchasesRepo,
        "get_active_invoice_for_user_product_for_update",
        _fake_get_active_invoice_for_user_product_for_update,
    )
    monkeypatch.setattr(purchase_init.PurchasesRepo, "create", _fake_create)
    monkeypatch.setattr(purchase_init, "_emit_purchase_event", _fake_emit_purchase_event)

    result = await purchase_init.init_purchase(
        SessionStub(),
        user_id=7,
        product_code="PREMIUM_MONTH",
        idempotency_key="idem-premium-upgrade",
        now_utc=NOW,
    )

    assert result.product_code == "PREMIUM_MONTH"
    assert created[0].product_code == "PREMIUM_MONTH"


@pytest.mark.asyncio
async def test_init_purchase_replays_existing_active_invoice_without_promo_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_invoice = purchase_model(idempotency_key="idem-existing-active")

    async def _fake_get_by_idempotency_key(_session, _idempotency_key: str):
        return None

    async def _fake_get_active_invoice_for_user_product_for_update(*_args, **_kwargs):
        return active_invoice

    async def _fail_validate_discount(*_args, **_kwargs):
        pytest.fail("promo validation should not run without promo_redemption_id")

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
        _fail_validate_discount,
    )

    result = await purchase_init.init_purchase(
        SessionStub(),
        user_id=7,
        product_code="ENERGY_10",
        idempotency_key="idem-existing-active",
        now_utc=NOW,
    )

    assert result.purchase_id == active_invoice.id
    assert result.idempotent_replay is True

