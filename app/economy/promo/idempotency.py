from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.promo_repo import PromoRepo
from app.economy.promo.errors import PromoInvalidError
from app.economy.promo.types import PromoRedeemResult


async def build_idempotent_result(
    session: AsyncSession,
    *,
    redemption: PromoRedemption,
) -> PromoRedeemResult:
    promo_code = await PromoRepo.get_code_by_id(session, redemption.promo_code_id)
    if promo_code is None:
        raise PromoInvalidError

    if promo_code.promo_type == "PREMIUM_GRANT":
        entitlement = None
        if redemption.grant_entitlement_id is not None:
            entitlement = await session.get(Entitlement, redemption.grant_entitlement_id)
        return PromoRedeemResult(
            redemption_id=redemption.id,
            result_type="PREMIUM_GRANT",
            idempotent_replay=True,
            premium_days=promo_code.grant_premium_days,
            premium_ends_at=(entitlement.ends_at if entitlement is not None else None),
        )

    if promo_code.promo_type == "PERCENT_DISCOUNT":
        return PromoRedeemResult(
            redemption_id=redemption.id,
            result_type="PERCENT_DISCOUNT",
            idempotent_replay=True,
            discount_percent=promo_code.discount_percent,
            reserved_until=redemption.reserved_until,
            target_scope=promo_code.target_scope,
        )

    raise PromoInvalidError
