from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.economy.premium_grants import grant_premium_days
from app.economy.promo.constants import PROMO_PREMIUM_SCOPE_BY_DAYS
from app.economy.promo.errors import PromoNotApplicableError


async def apply_premium_grant(
    session: AsyncSession,
    *,
    user_id: int,
    redemption: PromoRedemption,
    promo_code: PromoCode,
    now_utc: datetime,
) -> Entitlement:
    if promo_code.grant_premium_days is None or promo_code.grant_premium_days <= 0:
        raise PromoNotApplicableError

    grant_days = promo_code.grant_premium_days
    return await grant_premium_days(
        session,
        user_id=user_id,
        grant_days=grant_days,
        scope=PROMO_PREMIUM_SCOPE_BY_DAYS.get(grant_days, "PREMIUM_MONTH"),
        now_utc=now_utc,
        source="PROMO",
        entry_type="PROMO_GRANT",
        entitlement_idempotency_key=f"entitlement:promo:{redemption.id}",
        ledger_idempotency_key=f"promo:grant:{redemption.id}",
        metadata={
            "promo_redemption_id": str(redemption.id),
            "promo_code_id": promo_code.id,
            "grant_days": grant_days,
        },
    )
