from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.promo_repo import PromoRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.economy.purchases.catalog import get_product
from app.economy.purchases.errors import (
    PremiumDowngradeNotAllowedError,
    ProductNotFoundError,
    PurchaseInitValidationError,
)
from app.economy.purchases.types import PurchaseInitResult

from .builder import _as_init_result, _build_purchase
from .events import _emit_purchase_event
from .utilities import _premium_plan_rank
from .validation import (
    _validate_and_reserve_discount_redemption,
    _validate_streak_saver_purchase_limit,
)


async def init_purchase(
    session: AsyncSession,
    *,
    user_id: int,
    product_code: str,
    idempotency_key: str,
    now_utc: datetime,
    promo_redemption_id: UUID | None = None,
) -> PurchaseInitResult:
    product = get_product(product_code)
    if product is None:
        raise ProductNotFoundError

    existing = await PurchasesRepo.get_by_idempotency_key(session, idempotency_key)
    if existing is not None:
        return _as_init_result(existing, idempotent_replay=True)

    if product.product_code == "STREAK_SAVER_20":
        await _validate_streak_saver_purchase_limit(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )

    discount_stars_amount = 0
    applied_promo_code_id: int | None = None
    if promo_redemption_id is not None:
        discount_stars_amount, applied_promo_code_id = (
            await _validate_and_reserve_discount_redemption(
                session,
                redemption_id=promo_redemption_id,
                user_id=user_id,
                product=product,
                now_utc=now_utc,
            )
        )

    if product.product_type == "PREMIUM":
        active_premium = await EntitlementsRepo.get_active_premium_for_update(
            session, user_id, now_utc
        )
        if active_premium is not None:
            active_rank = _premium_plan_rank(active_premium.scope)
            next_rank = _premium_plan_rank(product.product_code)
            if next_rank <= active_rank:
                raise PremiumDowngradeNotAllowedError

    active_invoice = await PurchasesRepo.get_active_invoice_for_user_product(
        session,
        user_id=user_id,
        product_code=product.product_code,
    )
    if active_invoice is not None:
        return _as_init_result(active_invoice, idempotent_replay=True)

    try:
        purchase = await PurchasesRepo.create(
            session,
            purchase=_build_purchase(
                product,
                user_id=user_id,
                idempotency_key=idempotency_key,
                discount_stars_amount=discount_stars_amount,
                applied_promo_code_id=applied_promo_code_id,
                now_utc=now_utc,
            ),
            created_at=now_utc,
        )
    except IntegrityError:
        active_invoice = await PurchasesRepo.get_active_invoice_for_user_product(
            session,
            user_id=user_id,
            product_code=product.product_code,
        )
        if active_invoice is None:
            raise
        return _as_init_result(active_invoice, idempotent_replay=True)

    if promo_redemption_id is not None:
        redemption = await PromoRepo.get_redemption_by_id_for_update(session, promo_redemption_id)
        if redemption is None:
            raise PurchaseInitValidationError
        redemption.applied_purchase_id = purchase.id
        redemption.updated_at = now_utc

    await _emit_purchase_event(
        session,
        event_type="purchase_init_created",
        purchase=purchase,
        happened_at=now_utc,
    )

    return _as_init_result(purchase, idempotent_replay=False)
