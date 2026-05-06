from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.economy.purchases.errors import PurchaseInitValidationError
from app.economy.purchases.service import validation as purchase_validation
from app.economy.purchases.service.constants import PROMO_RESERVATION_TTL
from tests.purchase_service_test_helpers import NOW, SessionStub, product_spec, promo_code
from tests.type_helpers import build_promo_redemption


async def _zero_reserved(*_args, **_kwargs) -> int:
    return 0


def _patch_redemption(monkeypatch: pytest.MonkeyPatch, redemption) -> None:
    async def _fake_get_redemption_by_id_for_update(_session, _redemption_id):
        return redemption

    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "get_redemption_by_id_for_update",
        _fake_get_redemption_by_id_for_update,
    )


def _patch_code(monkeypatch: pytest.MonkeyPatch, code) -> None:
    async def _fake_get_code_by_id_for_update(_session, _promo_code_id: int):
        return code

    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "get_code_by_id_for_update",
        _fake_get_code_by_id_for_update,
    )


@pytest.mark.asyncio
async def test_validate_and_reserve_discount_redemption_reserves_active_discount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redemption = build_promo_redemption(status="VALIDATED", user_id=7)
    code = promo_code(id=redemption.promo_code_id)
    _patch_redemption(monkeypatch, redemption)
    _patch_code(monkeypatch, code)
    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "count_active_reserved_redemptions",
        _zero_reserved,
    )

    discount_stars_amount, promo_code_id = (
        await purchase_validation._validate_and_reserve_discount_redemption(
            SessionStub(),
            redemption_id=redemption.id,
            user_id=7,
            product=product_spec(),
            now_utc=NOW,
        )
    )

    assert discount_stars_amount == 2
    assert promo_code_id == code.id
    assert redemption.status == "RESERVED"
    assert redemption.reserved_until == NOW + PROMO_RESERVATION_TTL
    assert redemption.updated_at == NOW


@pytest.mark.parametrize(
    "promo_overrides",
    [
        {"status": "PAUSED"},
        {"valid_from": NOW - timedelta(days=3), "valid_until": NOW - timedelta(days=1)},
    ],
)
@pytest.mark.asyncio
async def test_validate_and_reserve_discount_redemption_rejects_inactive_or_expired_campaign(
    monkeypatch: pytest.MonkeyPatch,
    promo_overrides: dict[str, object],
) -> None:
    redemption = build_promo_redemption(status="VALIDATED", user_id=7)
    _patch_redemption(monkeypatch, redemption)
    _patch_code(monkeypatch, promo_code(id=redemption.promo_code_id, **promo_overrides))

    with pytest.raises(PurchaseInitValidationError):
        await purchase_validation._validate_and_reserve_discount_redemption(
            SessionStub(),
            redemption_id=redemption.id,
            user_id=7,
            product=product_spec(),
            now_utc=NOW,
        )

    assert redemption.status == "VALIDATED"
    assert redemption.reserved_until is None


@pytest.mark.parametrize("redemption_user_id", [None, 99])
@pytest.mark.asyncio
async def test_validate_and_reserve_discount_redemption_rejects_missing_or_wrong_user(
    monkeypatch: pytest.MonkeyPatch,
    redemption_user_id: int | None,
) -> None:
    redemption = (
        None
        if redemption_user_id is None
        else build_promo_redemption(status="VALIDATED", user_id=redemption_user_id)
    )
    _patch_redemption(monkeypatch, redemption)

    with pytest.raises(PurchaseInitValidationError):
        await purchase_validation._validate_and_reserve_discount_redemption(
            SessionStub(),
            redemption_id=uuid4(),
            user_id=7,
            product=product_spec(),
            now_utc=NOW,
        )


@pytest.mark.parametrize(
    "redemption_overrides",
    [
        {"applied_purchase_id": uuid4()},
        {"status": "APPLIED"},
    ],
)
@pytest.mark.asyncio
async def test_validate_and_reserve_discount_redemption_rejects_duplicate_redemption(
    monkeypatch: pytest.MonkeyPatch,
    redemption_overrides: dict[str, object],
) -> None:
    payload: dict[str, object] = {"status": "VALIDATED", "user_id": 7}
    payload.update(redemption_overrides)
    _patch_redemption(monkeypatch, build_promo_redemption(**payload))

    with pytest.raises(PurchaseInitValidationError):
        await purchase_validation._validate_and_reserve_discount_redemption(
            SessionStub(),
            redemption_id=uuid4(),
            user_id=7,
            product=product_spec(),
            now_utc=NOW,
        )


@pytest.mark.asyncio
async def test_validate_and_reserve_discount_redemption_rejects_expired_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redemption = build_promo_redemption(
        status="RESERVED",
        user_id=7,
        reserved_until=NOW - timedelta(seconds=1),
    )
    _patch_redemption(monkeypatch, redemption)

    with pytest.raises(PurchaseInitValidationError):
        await purchase_validation._validate_and_reserve_discount_redemption(
            SessionStub(),
            redemption_id=redemption.id,
            user_id=7,
            product=product_spec(),
            now_utc=NOW,
        )


@pytest.mark.parametrize(
    "code",
    [None, promo_code(promo_type="PREMIUM_GRANT"), promo_code(target_scope="PREMIUM_ANY")],
)
@pytest.mark.asyncio
async def test_validate_and_reserve_discount_redemption_rejects_invalid_promo_payload(
    monkeypatch: pytest.MonkeyPatch,
    code,
) -> None:
    _patch_redemption(monkeypatch, build_promo_redemption(status="VALIDATED", user_id=7))
    _patch_code(monkeypatch, code)

    with pytest.raises(PurchaseInitValidationError):
        await purchase_validation._validate_and_reserve_discount_redemption(
            SessionStub(),
            redemption_id=uuid4(),
            user_id=7,
            product=product_spec(),
            now_utc=NOW,
        )


@pytest.mark.asyncio
async def test_validate_and_reserve_discount_redemption_rejects_product_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redemption = build_promo_redemption(status="VALIDATED", user_id=7)
    _patch_redemption(monkeypatch, redemption)
    _patch_code(
        monkeypatch,
        promo_code(
            id=redemption.promo_code_id,
            applicable_products=["PREMIUM_MONTH"],
            target_scope="ANY",
        ),
    )

    with pytest.raises(PurchaseInitValidationError):
        await purchase_validation._validate_and_reserve_discount_redemption(
            SessionStub(),
            redemption_id=redemption.id,
            user_id=7,
            product=product_spec(),
            now_utc=NOW,
        )
