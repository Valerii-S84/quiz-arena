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


async def _zero_reserved(*_args, **_kwargs) -> int:
    return 0


def _purchase() -> Purchase:
    return cast(Purchase, SimpleNamespace(id=uuid4(), applied_promo_code_id=21))


def _patch_redemption(monkeypatch: pytest.MonkeyPatch, redemption) -> None:
    async def _fake_get_redemption_by_applied_purchase_id_for_update(_session, _purchase_id):
        return redemption

    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "get_redemption_by_applied_purchase_id_for_update",
        _fake_get_redemption_by_applied_purchase_id_for_update,
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
async def test_validate_reserved_discount_for_purchase_returns_active_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase()
    redemption = build_promo_redemption(
        status="RESERVED",
        applied_purchase_id=purchase.id,
        reserved_until=NOW + timedelta(minutes=5),
    )
    code = promo_code(id=21)
    _patch_redemption(monkeypatch, redemption)
    _patch_code(monkeypatch, code)
    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "count_active_reserved_redemptions",
        _zero_reserved,
    )

    result = await purchase_validation._validate_reserved_discount_for_purchase(
        SessionStub(),
        purchase=purchase,
        now_utc=NOW,
    )

    assert result == (redemption, code)


@pytest.mark.asyncio
async def test_validate_reserved_discount_for_purchase_rejects_missing_purchase_promo() -> None:
    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_validation._validate_reserved_discount_for_purchase(
            SessionStub(),
            purchase=cast(Purchase, SimpleNamespace(id=uuid4(), applied_promo_code_id=None)),
            now_utc=NOW,
        )


@pytest.mark.parametrize(
    "redemption",
    [
        None,
        build_promo_redemption(status="APPLIED", reserved_until=NOW + timedelta(minutes=5)),
        build_promo_redemption(status="RESERVED", reserved_until=None),
        build_promo_redemption(status="RESERVED", reserved_until=NOW - timedelta(seconds=1)),
    ],
)
@pytest.mark.asyncio
async def test_validate_reserved_discount_for_purchase_rejects_invalid_reservation_state(
    monkeypatch: pytest.MonkeyPatch,
    redemption,
) -> None:
    _patch_redemption(monkeypatch, redemption)

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_validation._validate_reserved_discount_for_purchase(
            SessionStub(),
            purchase=_purchase(),
            now_utc=NOW,
        )


@pytest.mark.asyncio
async def test_validate_reserved_discount_for_purchase_rejects_capacity_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase()
    redemption = build_promo_redemption(
        status="RESERVED",
        applied_purchase_id=purchase.id,
        reserved_until=NOW + timedelta(minutes=5),
    )
    _patch_redemption(monkeypatch, redemption)
    _patch_code(monkeypatch, promo_code(id=21, max_total_uses=1, used_total=1))
    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "count_active_reserved_redemptions",
        _zero_reserved,
    )

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_validation._validate_reserved_discount_for_purchase(
            SessionStub(),
            purchase=purchase,
            now_utc=NOW,
        )
