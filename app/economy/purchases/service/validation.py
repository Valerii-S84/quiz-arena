from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase
from app.db.repo.promo_repo import PromoRepo
from app.db.repo.streak_repo import StreakRepo
from app.economy.purchases.catalog import ProductSpec
from app.economy.purchases.errors import (
    PurchaseInitValidationError,
    PurchasePrecheckoutValidationError,
    StreakSaverPurchaseLimitError,
)

from .constants import PROMO_RESERVATION_TTL, STREAK_SAVER_PURCHASE_LOCK_WINDOW
from .utilities import _calculate_discount_amount_for_promo, _is_promo_scope_applicable


async def _ensure_discount_capacity_available(
    session: AsyncSession,
    *,
    promo_code: PromoCode,
    redemption_id: UUID,
    now_utc: datetime,
    error_type: type[Exception],
) -> None:
    if promo_code.max_total_uses is None:
        return

    reserved_total = await PromoRepo.count_active_reserved_redemptions(
        session,
        promo_code_id=promo_code.id,
        now_utc=now_utc,
        exclude_redemption_id=redemption_id,
    )
    if promo_code.used_total + reserved_total >= promo_code.max_total_uses:
        raise error_type


async def _validate_streak_saver_purchase_limit(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
) -> None:
    streak_state = await StreakRepo.get_by_user_id_for_update(session, user_id)
    if streak_state is None:
        return

    last_purchase_at = streak_state.streak_saver_last_purchase_at
    if last_purchase_at is None:
        return

    if now_utc < last_purchase_at + STREAK_SAVER_PURCHASE_LOCK_WINDOW:
        raise StreakSaverPurchaseLimitError


async def _validate_and_reserve_discount_redemption(
    session: AsyncSession,
    *,
    redemption_id: UUID,
    user_id: int,
    product: ProductSpec,
    now_utc: datetime,
) -> tuple[int, int]:
    redemption = await PromoRepo.get_redemption_by_id_for_update(session, redemption_id)
    if redemption is None or redemption.user_id != user_id:
        raise PurchaseInitValidationError
    if redemption.applied_purchase_id is not None:
        raise PurchaseInitValidationError
    if redemption.status not in {"VALIDATED", "RESERVED"}:
        raise PurchaseInitValidationError

    if redemption.reserved_until is not None and redemption.reserved_until <= now_utc:
        raise PurchaseInitValidationError

    promo_code = await PromoRepo.get_code_by_id_for_update(session, redemption.promo_code_id)
    if promo_code is None:
        raise PurchaseInitValidationError
    if promo_code.promo_type != "PERCENT_DISCOUNT":
        raise PurchaseInitValidationError
    if promo_code.status != "ACTIVE":
        raise PurchaseInitValidationError
    if not (promo_code.valid_from <= now_utc < promo_code.valid_until):
        raise PurchaseInitValidationError
    if not _is_promo_scope_applicable(promo_code, product=product):
        raise PurchaseInitValidationError
    await _ensure_discount_capacity_available(
        session,
        promo_code=promo_code,
        redemption_id=redemption.id,
        now_utc=now_utc,
        error_type=PurchaseInitValidationError,
    )

    discount_stars_amount = _calculate_discount_amount_for_promo(
        product.stars_amount,
        promo_code=promo_code,
    )
    redemption.status = "RESERVED"
    redemption.reserved_until = now_utc + PROMO_RESERVATION_TTL
    redemption.updated_at = now_utc
    return discount_stars_amount, promo_code.id


async def _validate_reserved_discount_for_purchase(
    session: AsyncSession,
    *,
    purchase: Purchase,
    now_utc: datetime,
) -> tuple[PromoRedemption, PromoCode]:
    if purchase.applied_promo_code_id is None:
        raise PurchasePrecheckoutValidationError

    redemption = await PromoRepo.get_redemption_by_applied_purchase_id_for_update(
        session, purchase.id
    )
    if redemption is None:
        raise PurchasePrecheckoutValidationError
    if redemption.status != "RESERVED":
        raise PurchasePrecheckoutValidationError
    if redemption.reserved_until is None or redemption.reserved_until <= now_utc:
        raise PurchasePrecheckoutValidationError

    promo_code = await PromoRepo.get_code_by_id_for_update(session, purchase.applied_promo_code_id)
    if promo_code is None:
        raise PurchasePrecheckoutValidationError
    if promo_code.promo_type != "PERCENT_DISCOUNT":
        raise PurchasePrecheckoutValidationError
    if promo_code.status != "ACTIVE":
        raise PurchasePrecheckoutValidationError
    if not (promo_code.valid_from <= now_utc < promo_code.valid_until):
        raise PurchasePrecheckoutValidationError
    await _ensure_discount_capacity_available(
        session,
        promo_code=promo_code,
        redemption_id=redemption.id,
        now_utc=now_utc,
        error_type=PurchasePrecheckoutValidationError,
    )

    return redemption, promo_code
