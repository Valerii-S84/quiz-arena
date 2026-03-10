from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.economy.promo.constants import PROMO_DISCOUNT_RESERVATION_TTL
from app.economy.promo.runtime import (
    resolve_applicable_products,
    resolve_discount_type,
    resolve_discount_value,
)
from app.economy.promo.types import PromoRedeemResult

PremiumGrantApplier = Callable[..., Awaitable[Entitlement]]


def build_validation_snapshot(*, promo_code: PromoCode, now_utc: datetime) -> dict[str, object]:
    return {
        "promo_type": promo_code.promo_type,
        "target_scope": promo_code.target_scope,
        "discount_type": resolve_discount_type(promo_code),
        "discount_value": resolve_discount_value(promo_code),
        "applicable_products": resolve_applicable_products(promo_code) or [],
        "validated_at": now_utc.isoformat(),
    }


async def apply_premium_grant_redemption(
    session: AsyncSession,
    *,
    user_id: int,
    redemption: PromoRedemption,
    promo_code: PromoCode,
    now_utc: datetime,
    apply_premium_grant: PremiumGrantApplier,
) -> PromoRedeemResult:
    entitlement = await apply_premium_grant(
        session,
        user_id=user_id,
        redemption=redemption,
        promo_code=promo_code,
        now_utc=now_utc,
    )
    redemption.status = "APPLIED"
    redemption.applied_at = now_utc
    redemption.grant_entitlement_id = entitlement.id
    redemption.updated_at = now_utc
    promo_code.used_total += 1
    promo_code.updated_at = now_utc
    return PromoRedeemResult(
        redemption_id=redemption.id,
        result_type="PREMIUM_GRANT",
        idempotent_replay=False,
        premium_days=promo_code.grant_premium_days,
        premium_ends_at=entitlement.ends_at,
    )


def reserve_discount_redemption(
    *,
    redemption: PromoRedemption,
    promo_code: PromoCode,
    now_utc: datetime,
) -> PromoRedeemResult:
    reserved_until = now_utc + PROMO_DISCOUNT_RESERVATION_TTL
    redemption.status = "RESERVED"
    redemption.reserved_until = reserved_until
    redemption.updated_at = now_utc
    return PromoRedeemResult(
        redemption_id=redemption.id,
        result_type="PERCENT_DISCOUNT",
        idempotent_replay=False,
        discount_type=resolve_discount_type(promo_code),
        discount_value=resolve_discount_value(promo_code),
        discount_percent=promo_code.discount_percent,
        reserved_until=reserved_until,
        target_scope=promo_code.target_scope,
        applicable_products=resolve_applicable_products(promo_code),
    )
