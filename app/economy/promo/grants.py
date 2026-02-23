from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.ledger_repo import LedgerRepo
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
    active_entitlement = await EntitlementsRepo.get_active_premium_for_update(
        session, user_id, now_utc
    )
    if active_entitlement is not None:
        base_end = (
            active_entitlement.ends_at
            if active_entitlement.ends_at and active_entitlement.ends_at > now_utc
            else now_utc
        )
        active_entitlement.ends_at = base_end + timedelta(days=grant_days)
        active_entitlement.updated_at = now_utc
        entitlement = active_entitlement
    else:
        entitlement = await EntitlementsRepo.create(
            session,
            entitlement=Entitlement(
                user_id=user_id,
                entitlement_type="PREMIUM",
                scope=PROMO_PREMIUM_SCOPE_BY_DAYS.get(grant_days, "PREMIUM_MONTH"),
                status="ACTIVE",
                starts_at=now_utc,
                ends_at=now_utc + timedelta(days=grant_days),
                source_purchase_id=None,
                idempotency_key=f"entitlement:promo:{redemption.id}",
                metadata_={
                    "promo_redemption_id": str(redemption.id),
                    "promo_code_id": promo_code.id,
                },
                created_at=now_utc,
                updated_at=now_utc,
            ),
        )

    await LedgerRepo.create(
        session,
        entry=LedgerEntry(
            user_id=user_id,
            purchase_id=None,
            entry_type="PROMO_GRANT",
            asset="PREMIUM",
            direction="CREDIT",
            amount=grant_days,
            balance_after=None,
            source="PROMO",
            idempotency_key=f"promo:grant:{redemption.id}",
            metadata_={
                "promo_redemption_id": str(redemption.id),
                "promo_code_id": promo_code.id,
                "grant_days": grant_days,
            },
            created_at=now_utc,
        ),
    )
    return entitlement
