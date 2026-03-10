from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ledger_entries import LedgerEntry
from app.db.models.mode_access import ModeAccess
from app.db.models.purchases import Purchase
from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.mode_access_repo import ModeAccessRepo
from app.db.repo.streak_repo import StreakRepo
from app.economy.energy.service import EnergyService
from app.economy.purchases.catalog import MEGA_PACK_MODE_CODES, ProductSpec

from .entitlements import _apply_premium_entitlement
from .events import _emit_purchase_event
from .validation import _validate_reserved_discount_for_purchase


def build_asset_breakdown(product: ProductSpec) -> dict[str, object]:
    breakdown: dict[str, object] = {}
    if product.energy_credit > 0:
        breakdown["paid_energy"] = product.energy_credit
    if product.premium_days > 0:
        breakdown["premium_days"] = product.premium_days
    if product.grants_mega_mode_access:
        breakdown["mode_codes"] = list(MEGA_PACK_MODE_CODES)
    if product.grants_streak_saver:
        breakdown["streak_saver_tokens"] = 1
    if product.friend_challenge_tickets > 0:
        breakdown["friend_challenge_tickets"] = product.friend_challenge_tickets
    return breakdown


async def credit_purchase_assets(
    session: AsyncSession,
    *,
    user_id: int,
    purchase: Purchase,
    product: ProductSpec,
    now_utc: datetime,
) -> None:
    if product.product_type == "PREMIUM":
        await _apply_premium_entitlement(
            session,
            user_id=user_id,
            purchase=purchase,
            product=product,
            now_utc=now_utc,
        )

    if product.energy_credit > 0:
        await EnergyService.credit_paid_energy(
            session,
            user_id=user_id,
            amount=product.energy_credit,
            idempotency_key=f"credit:energy:{purchase.id}",
            now_utc=now_utc,
            write_ledger_entry=False,
        )

    if product.grants_streak_saver:
        await StreakRepo.add_streak_saver_token(session, user_id=user_id, now_utc=now_utc)

    if product.grants_mega_mode_access:
        for mode_code in MEGA_PACK_MODE_CODES:
            latest_end = await ModeAccessRepo.get_latest_active_end(
                session,
                user_id=user_id,
                mode_code=mode_code,
                source="MEGA_PACK",
                now_utc=now_utc,
            )
            starts_at = latest_end if latest_end is not None and latest_end > now_utc else now_utc
            ends_at = starts_at + timedelta(hours=24)
            await ModeAccessRepo.create(
                session,
                mode_access=ModeAccess(
                    user_id=user_id,
                    mode_code=mode_code,
                    source="MEGA_PACK",
                    starts_at=starts_at,
                    ends_at=ends_at,
                    status="ACTIVE",
                    source_purchase_id=purchase.id,
                    idempotency_key=f"mode_access:{purchase.id}:{mode_code}",
                    created_at=now_utc,
                ),
            )

    if purchase.applied_promo_code_id is not None:
        promo_redemption, promo_code = await _validate_reserved_discount_for_purchase(
            session,
            purchase=purchase,
            now_utc=now_utc,
        )
        if promo_redemption.status != "APPLIED":
            promo_redemption.status = "APPLIED"
            promo_redemption.applied_at = now_utc
            promo_redemption.updated_at = now_utc
            promo_code.used_total += 1
            promo_code.updated_at = now_utc

    await LedgerRepo.create(
        session,
        entry=LedgerEntry(
            user_id=user_id,
            purchase_id=purchase.id,
            entry_type="PURCHASE_CREDIT",
            asset="PURCHASE",
            direction="CREDIT",
            amount=purchase.stars_amount,
            balance_after=None,
            source="PURCHASE",
            idempotency_key=f"credit:purchase:{purchase.id}",
            metadata_={
                "product_code": product.product_code,
                "asset_breakdown": build_asset_breakdown(product),
            },
            created_at=now_utc,
        ),
    )

    purchase.status = "CREDITED"
    purchase.credited_at = now_utc
    await _emit_purchase_event(
        session,
        event_type="purchase_credited",
        purchase=purchase,
        happened_at=now_utc,
    )
