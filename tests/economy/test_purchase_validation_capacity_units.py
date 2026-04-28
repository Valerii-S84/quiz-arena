from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.economy.purchases.errors import PurchaseInitValidationError, StreakSaverPurchaseLimitError
from app.economy.purchases.service import validation as purchase_validation
from tests.purchase_service_test_helpers import NOW, SessionStub, promo_code


@pytest.mark.asyncio
async def test_ensure_discount_capacity_available_enforces_usage_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code = promo_code(max_total_uses=2, used_total=1)
    redemption_id = uuid4()

    async def _fake_count_active_reserved_redemptions(*_args, **_kwargs) -> int:
        return 1

    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "count_active_reserved_redemptions",
        _fake_count_active_reserved_redemptions,
    )

    with pytest.raises(PurchaseInitValidationError):
        await purchase_validation._ensure_discount_capacity_available(
            SessionStub(),
            promo_code=code,
            redemption_id=redemption_id,
            now_utc=NOW,
            error_type=PurchaseInitValidationError,
        )


@pytest.mark.asyncio
async def test_ensure_discount_capacity_available_skips_unlimited_campaign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fail_count_active_reserved_redemptions(*_args, **_kwargs) -> int:
        pytest.fail("capacity lookup should not run for unlimited campaigns")

    monkeypatch.setattr(
        purchase_validation.PromoRepo,
        "count_active_reserved_redemptions",
        _fail_count_active_reserved_redemptions,
    )

    await purchase_validation._ensure_discount_capacity_available(
        SessionStub(),
        promo_code=promo_code(max_total_uses=None, used_total=99),
        redemption_id=uuid4(),
        now_utc=NOW,
        error_type=PurchaseInitValidationError,
    )


@pytest.mark.parametrize(
    "streak_state",
    [
        None,
        SimpleNamespace(streak_saver_last_purchase_at=None),
        SimpleNamespace(streak_saver_last_purchase_at=NOW - timedelta(days=8)),
    ],
)
@pytest.mark.asyncio
async def test_validate_streak_saver_purchase_limit_allows_unlocked_users(
    monkeypatch: pytest.MonkeyPatch,
    streak_state,
) -> None:
    async def _fake_get_by_user_id_for_update(_session, user_id: int):
        assert user_id == 7
        return streak_state

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
async def test_validate_streak_saver_purchase_limit_rejects_recent_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace(streak_saver_last_purchase_at=NOW - timedelta(minutes=1))

    async def _fake_get_by_user_id_for_update(_session, _user_id: int):
        return state

    monkeypatch.setattr(
        purchase_validation.StreakRepo,
        "get_by_user_id_for_update",
        _fake_get_by_user_id_for_update,
    )

    with pytest.raises(StreakSaverPurchaseLimitError):
        await purchase_validation._validate_streak_saver_purchase_limit(
            SessionStub(),
            user_id=7,
            now_utc=NOW,
        )
