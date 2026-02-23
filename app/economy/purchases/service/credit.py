from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ledger_entries import LedgerEntry
from app.db.models.mode_access import ModeAccess
from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.mode_access_repo import ModeAccessRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.streak_repo import StreakRepo
from app.economy.energy.service import EnergyService
from app.economy.purchases.catalog import MEGA_PACK_MODE_CODES, get_product
from app.economy.purchases.errors import (
    ProductNotFoundError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
)
from app.economy.purchases.types import PurchaseCreditResult

from .entitlements import _apply_premium_entitlement
from .events import _emit_purchase_event
from .validation import _validate_reserved_discount_for_purchase


async def apply_successful_payment(
    session: AsyncSession,
    *,
    user_id: int,
    invoice_payload: str,
    telegram_payment_charge_id: str,
    raw_successful_payment: dict[str, object],
    now_utc: datetime,
) -> PurchaseCreditResult:
    purchase = await PurchasesRepo.get_by_invoice_payload_for_update(session, invoice_payload)
    if purchase is None or purchase.user_id != user_id:
        raise PurchaseNotFoundError

    if purchase.status == "CREDITED":
        return PurchaseCreditResult(
            purchase_id=purchase.id,
            product_code=purchase.product_code,
            status=purchase.status,
            idempotent_replay=True,
        )

    if purchase.status not in {
        "PRECHECKOUT_OK",
        "INVOICE_SENT",
        "CREATED",
        "PAID_UNCREDITED",
    }:
        raise PurchasePrecheckoutValidationError

    previous_status = purchase.status
    purchase.telegram_payment_charge_id = telegram_payment_charge_id
    purchase.raw_successful_payment = raw_successful_payment
    purchase.status = "PAID_UNCREDITED"
    if purchase.paid_at is None or previous_status != "PAID_UNCREDITED":
        purchase.paid_at = now_utc
    if previous_status != "PAID_UNCREDITED":
        await _emit_purchase_event(
            session,
            event_type="purchase_paid_uncredited",
            purchase=purchase,
            happened_at=now_utc,
            extra_payload={"previous_status": previous_status},
        )

    product = get_product(purchase.product_code)
    if product is None:
        raise ProductNotFoundError

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
        )

    if product.friend_challenge_tickets > 0:
        await LedgerRepo.create(
            session,
            entry=LedgerEntry(
                user_id=user_id,
                purchase_id=purchase.id,
                entry_type="PURCHASE_CREDIT",
                asset="MODE_ACCESS",
                direction="CREDIT",
                amount=product.friend_challenge_tickets,
                balance_after=None,
                source="PURCHASE",
                idempotency_key=f"credit:friend_challenge_ticket:{purchase.id}",
                metadata_={"product_code": product.product_code},
                created_at=now_utc,
            ),
        )

    if product.grants_streak_saver:
        streak_state = await StreakRepo.add_streak_saver_token(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )
        await LedgerRepo.create(
            session,
            entry=LedgerEntry(
                user_id=user_id,
                purchase_id=purchase.id,
                entry_type="PURCHASE_CREDIT",
                asset="STREAK_SAVER",
                direction="CREDIT",
                amount=1,
                balance_after=streak_state.streak_saver_tokens,
                source="PURCHASE",
                idempotency_key=f"credit:streak_saver:{purchase.id}",
                metadata_={},
                created_at=now_utc,
            ),
        )

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
            if (
                promo_code.max_total_uses is not None
                and promo_code.used_total >= promo_code.max_total_uses
            ):
                raise PurchasePrecheckoutValidationError
            promo_redemption.status = "APPLIED"
            promo_redemption.applied_at = now_utc
            promo_redemption.updated_at = now_utc
            promo_code.used_total += 1
            promo_code.updated_at = now_utc

    purchase.status = "CREDITED"
    purchase.credited_at = now_utc
    await _emit_purchase_event(
        session,
        event_type="purchase_credited",
        purchase=purchase,
        happened_at=now_utc,
    )

    return PurchaseCreditResult(
        purchase_id=purchase.id,
        product_code=purchase.product_code,
        status=purchase.status,
        idempotent_replay=False,
    )
