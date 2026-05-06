from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from app.db.models.purchases import Purchase
from app.economy.purchases.errors import PurchasePrecheckoutValidationError
from app.economy.purchases.service import validation as purchase_validation
from tests.purchase_service_test_helpers import NOW, SessionStub, promo_code
from tests.type_helpers import build_promo_redemption


def _purchase() -> Purchase:
    return cast(Purchase, SimpleNamespace(id=uuid4(), applied_promo_code_id=21))


def _patch_redemption(monkeypatch: pytest.MonkeyPatch, purchase: Purchase) -> None:
    redemption = build_promo_redemption(
        status="RESERVED",
        applied_purchase_id=purchase.id,
        reserved_until=NOW + timedelta(minutes=5),
    )

    async def _fake_get_redemption_by_applied_purchase_id_for_update(_session, _purchase_id):
        return redemption

    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "get_redemption_by_applied_purchase_id_for_update",
        _fake_get_redemption_by_applied_purchase_id_for_update,
    )


@pytest.mark.parametrize(
    "code",
    [
        None,
        promo_code(promo_type="PREMIUM_GRANT"),
        promo_code(status="PAUSED"),
        promo_code(valid_from=NOW + timedelta(minutes=1)),
        promo_code(valid_until=NOW - timedelta(minutes=1)),
    ],
)
@pytest.mark.asyncio
async def test_validate_reserved_discount_for_purchase_rejects_invalid_promo_payload(
    monkeypatch: pytest.MonkeyPatch,
    code,
) -> None:
    purchase = _purchase()
    _patch_redemption(monkeypatch, purchase)

    async def _fake_get_code_by_id_for_update(_session, _promo_code_id: int):
        return code

    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "get_code_by_id_for_update",
        _fake_get_code_by_id_for_update,
    )

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_validation._validate_reserved_discount_for_purchase(
            SessionStub(),
            purchase=purchase,
            now_utc=NOW,
        )


@pytest.mark.asyncio
async def test_validate_reserved_discount_for_purchase_skips_capacity_lookup_for_unlimited_campaign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase()
    _patch_redemption(monkeypatch, purchase)

    async def _fake_get_code_by_id_for_update(_session, _promo_code_id: int):
        return promo_code(id=21, max_total_uses=None, used_total=999)

    async def _fail_count_active_reserved_redemptions(*_args, **_kwargs) -> int:
        pytest.fail("capacity lookup should not run for unlimited campaigns")

    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "get_code_by_id_for_update",
        _fake_get_code_by_id_for_update,
    )
    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "count_active_reserved_redemptions",
        _fail_count_active_reserved_redemptions,
    )

    redemption, code = await purchase_validation._validate_reserved_discount_for_purchase(
        SessionStub(),
        purchase=purchase,
        now_utc=NOW,
    )

    assert redemption.applied_purchase_id == purchase.id
    assert code.max_total_uses is None


@pytest.mark.asyncio
async def test_validate_reserved_discount_for_purchase_accepts_valid_until_boundary_before_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase()
    _patch_redemption(monkeypatch, purchase)

    async def _fake_get_code_by_id_for_update(_session, _promo_code_id: int):
        return promo_code(
            id=21,
            valid_from=NOW - timedelta(days=1),
            valid_until=NOW + timedelta(seconds=1),
        )

    async def _zero_reserved(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "get_code_by_id_for_update",
        _fake_get_code_by_id_for_update,
    )
    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "count_active_reserved_redemptions",
        _zero_reserved,
    )

    redemption, code = await purchase_validation._validate_reserved_discount_for_purchase(
        SessionStub(),
        purchase=purchase,
        now_utc=NOW,
    )

    assert redemption.applied_purchase_id == purchase.id
    assert code.id == 21
