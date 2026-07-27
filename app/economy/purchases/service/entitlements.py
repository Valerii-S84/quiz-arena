from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement
from app.db.models.purchases import Purchase
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.economy.purchases.catalog import ProductSpec
from app.economy.purchases.errors import PurchasePrecheckoutValidationError

from .utilities import _premium_plan_rank


async def _apply_premium_entitlement(
    session: AsyncSession,
    *,
    user_id: int,
    purchase: Purchase,
    product: ProductSpec,
    now_utc: datetime,
) -> None:
    if product.premium_days <= 0:
        raise PurchasePrecheckoutValidationError

    existing_entitlement = await EntitlementsRepo.get_by_source_purchase_id_for_update(
        session,
        purchase_id=purchase.id,
        entitlement_type="PREMIUM",
    )
    if existing_entitlement is not None:
        return

    active_entitlement = await EntitlementsRepo.get_premium_with_active_status_for_update(
        session, user_id
    )
    starts_at = now_utc
    ends_at = now_utc + timedelta(days=product.premium_days)

    if (
        active_entitlement is not None
        and active_entitlement.ends_at is not None
        and active_entitlement.ends_at <= now_utc
    ):
        active_entitlement.status = "EXPIRED"
        active_entitlement.updated_at = now_utc
        await session.flush()
        active_entitlement = None

    if active_entitlement is not None:
        active_rank = _premium_plan_rank(active_entitlement.scope)
        next_rank = _premium_plan_rank(product.product_code)
        if next_rank <= active_rank:
            raise PurchasePrecheckoutValidationError

        active_end = (
            active_entitlement.ends_at if active_entitlement.ends_at is not None else now_utc
        )
        if active_end > now_utc:
            ends_at = active_end + timedelta(days=product.premium_days)
        active_entitlement.status = "REVOKED"
        active_entitlement.updated_at = now_utc

    await EntitlementsRepo.create(
        session,
        entitlement=Entitlement(
            user_id=user_id,
            entitlement_type="PREMIUM",
            scope=product.product_code,
            status="ACTIVE",
            starts_at=starts_at,
            ends_at=ends_at,
            source_purchase_id=purchase.id,
            idempotency_key=f"entitlement:premium:{purchase.id}",
            metadata_={},
            created_at=now_utc,
            updated_at=now_utc,
        ),
    )
