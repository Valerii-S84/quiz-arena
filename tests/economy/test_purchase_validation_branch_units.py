from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.economy.purchases.service import validation as purchase_validation
from app.economy.purchases.service.constants import (
    PROMO_RESERVATION_TTL,
    STREAK_SAVER_PURCHASE_LOCK_WINDOW,
)
from tests.purchase_service_test_helpers import NOW, SessionStub, product_spec, promo_code
from tests.type_helpers import build_promo_redemption


@pytest.mark.asyncio
async def test_ensure_discount_capacity_available_allows_remaining_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_count_active_reserved_redemptions(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "count_active_reserved_redemptions",
        _fake_count_active_reserved_redemptions,
    )

    await purchase_validation._ensure_discount_capacity_available(
        SessionStub(),
        promo_code=promo_code(max_total_uses=2, used_total=1),
        redemption_id=uuid4(),
        now_utc=NOW,
        error_type=RuntimeError,
    )


@pytest.mark.asyncio
async def test_validate_streak_saver_purchase_limit_allows_exact_unlock_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace(streak_saver_last_purchase_at=NOW - STREAK_SAVER_PURCHASE_LOCK_WINDOW)

    async def _fake_get_by_user_id_for_update(_session, _user_id: int):
        return state

    monkeypatch.setattr(
        purchase_validation.StreakRepo,
        "get_by_user_id_for_update",
        _fake_get_by_user_id_for_update,
    )

    await purchase_validation._validate_streak_saver_purchase_limit(
        SessionStub(),
        user_id=7,
        now_utc=NOW,
    )


@pytest.mark.asyncio
async def test_validate_and_reserve_discount_redemption_keeps_reserved_status_for_active_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redemption = build_promo_redemption(
        status="RESERVED",
        user_id=7,
        reserved_until=NOW + timedelta(minutes=2),
    )
    code = promo_code(id=redemption.promo_code_id)

    async def _fake_get_redemption_by_id_for_update(_session, _redemption_id):
        return redemption

    async def _fake_get_code_by_id_for_update(_session, _promo_code_id: int):
        return code

    async def _zero_reserved(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "get_redemption_by_id_for_update",
        _fake_get_redemption_by_id_for_update,
    )
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
