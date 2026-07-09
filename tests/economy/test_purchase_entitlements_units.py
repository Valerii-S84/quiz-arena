from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.db.models.entitlements import Entitlement
from app.economy.purchases.catalog import ProductSpec
from app.economy.purchases.errors import PurchasePrecheckoutValidationError
from app.economy.purchases.service import entitlements as purchase_entitlements
from tests.purchase_service_test_helpers import NOW, SessionStub, purchase_model


def _premium_product(product_code: str = "PREMIUM_MONTH", premium_days: int = 30) -> ProductSpec:
    return ProductSpec(
        product_code=product_code,
        product_type="PREMIUM",
        title=product_code,
        description=product_code,
        stars_amount=99,
        energy_credit=0,
        premium_days=premium_days,
    )


@pytest.mark.asyncio
async def test_apply_premium_entitlement_rejects_non_positive_duration() -> None:
    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_entitlements._apply_premium_entitlement(
            SessionStub(),
            user_id=7,
            purchase=purchase_model(),
            product=_premium_product(premium_days=0),
            now_utc=NOW,
        )


@pytest.mark.asyncio
async def test_apply_premium_entitlement_creates_new_entitlement_without_active_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Entitlement] = []

    async def _fake_get_by_source_purchase_id_for_update(
        _session,
        *,
        purchase_id,
        entitlement_type: str,
    ):
        del purchase_id, entitlement_type
        return None

    async def _fake_get_active_premium_for_update(_session, user_id: int, now_utc):
        assert user_id == 7
        assert now_utc == NOW
        return None

    async def _fake_create(_session, *, entitlement: Entitlement):
        created.append(entitlement)
        return entitlement

    monkeypatch.setattr(
        purchase_entitlements.EntitlementsRepo,
        "get_by_source_purchase_id_for_update",
        _fake_get_by_source_purchase_id_for_update,
    )
    monkeypatch.setattr(
        purchase_entitlements.EntitlementsRepo,
        "get_active_premium_for_update",
        _fake_get_active_premium_for_update,
    )
    monkeypatch.setattr(purchase_entitlements.EntitlementsRepo, "create", _fake_create)

    purchase = purchase_model(product_code="PREMIUM_MONTH", product_type="PREMIUM", stars_amount=99)
    await purchase_entitlements._apply_premium_entitlement(
        SessionStub(),
        user_id=7,
        purchase=purchase,
        product=_premium_product(),
        now_utc=NOW,
    )

    assert created[0].scope == "PREMIUM_MONTH"
    assert created[0].status == "ACTIVE"
    assert created[0].starts_at == NOW
    assert created[0].ends_at == NOW + timedelta(days=30)
    assert created[0].source_purchase_id == purchase.id


@pytest.mark.asyncio
async def test_apply_premium_entitlement_rejects_non_upgrade_active_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_entitlement = SimpleNamespace(scope="PREMIUM_MONTH", ends_at=NOW + timedelta(days=5))

    async def _fake_get_by_source_purchase_id_for_update(*_args, **_kwargs):
        return None

    async def _fake_get_active_premium_for_update(_session, _user_id: int, _now_utc):
        return active_entitlement

    monkeypatch.setattr(
        purchase_entitlements.EntitlementsRepo,
        "get_by_source_purchase_id_for_update",
        _fake_get_by_source_purchase_id_for_update,
    )
    monkeypatch.setattr(
        purchase_entitlements.EntitlementsRepo,
        "get_active_premium_for_update",
        _fake_get_active_premium_for_update,
    )

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_entitlements._apply_premium_entitlement(
            SessionStub(),
            user_id=7,
            purchase=purchase_model(product_code="PREMIUM_WEEK", product_type="PREMIUM"),
            product=_premium_product(product_code="PREMIUM_WEEK", premium_days=7),
            now_utc=NOW,
        )


@pytest.mark.asyncio
async def test_apply_premium_entitlement_revokes_active_plan_and_extends_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_entitlement = SimpleNamespace(
        scope="PREMIUM_WEEK",
        ends_at=NOW + timedelta(days=3),
        status="ACTIVE",
        updated_at=None,
    )
    created: list[Entitlement] = []

    async def _fake_get_by_source_purchase_id_for_update(*_args, **_kwargs):
        return None

    async def _fake_get_active_premium_for_update(_session, _user_id: int, _now_utc):
        return active_entitlement

    async def _fake_create(_session, *, entitlement: Entitlement):
        created.append(entitlement)
        return entitlement

    monkeypatch.setattr(
        purchase_entitlements.EntitlementsRepo,
        "get_by_source_purchase_id_for_update",
        _fake_get_by_source_purchase_id_for_update,
    )
    monkeypatch.setattr(
        purchase_entitlements.EntitlementsRepo,
        "get_active_premium_for_update",
        _fake_get_active_premium_for_update,
    )
    monkeypatch.setattr(purchase_entitlements.EntitlementsRepo, "create", _fake_create)

    purchase = purchase_model(product_code="PREMIUM_MONTH", product_type="PREMIUM", stars_amount=99)
    await purchase_entitlements._apply_premium_entitlement(
        SessionStub(),
        user_id=7,
        purchase=purchase,
        product=_premium_product(),
        now_utc=NOW,
    )

    assert active_entitlement.status == "REVOKED"
    assert active_entitlement.updated_at == NOW
    assert created[0].ends_at == active_entitlement.ends_at + timedelta(days=30)


@pytest.mark.asyncio
async def test_apply_premium_entitlement_returns_existing_source_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_entitlement = SimpleNamespace(source_purchase_id="purchase")

    async def _fake_get_by_source_purchase_id_for_update(*_args, **_kwargs):
        return existing_entitlement

    async def _fail_get_active(*_args, **_kwargs):
        raise AssertionError("existing source purchase entitlement should short-circuit")

    async def _fail_create(*_args, **_kwargs):
        raise AssertionError("existing source purchase entitlement should not create duplicate")

    monkeypatch.setattr(
        purchase_entitlements.EntitlementsRepo,
        "get_by_source_purchase_id_for_update",
        _fake_get_by_source_purchase_id_for_update,
    )
    monkeypatch.setattr(
        purchase_entitlements.EntitlementsRepo,
        "get_active_premium_for_update",
        _fail_get_active,
    )
    monkeypatch.setattr(purchase_entitlements.EntitlementsRepo, "create", _fail_create)

    await purchase_entitlements._apply_premium_entitlement(
        SessionStub(),
        user_id=7,
        purchase=purchase_model(product_code="PREMIUM_MONTH", product_type="PREMIUM"),
        product=_premium_product(),
        now_utc=NOW,
    )
