from __future__ import annotations

from datetime import datetime

from aiogram.types import SuccessfulPayment, User

from app.bot.handlers.payments_helpers import (
    extract_offer_impression_id_from_purchase_idempotency_key,
)
from app.db.session import SessionLocal
from app.economy.offers.service import OfferService
from app.economy.purchases.service import PurchaseService
from app.services.user_onboarding import UserOnboardingService


async def apply_zero_cost_purchase(
    *,
    telegram_user: User,
    purchase_id,
    now_utc: datetime,
) -> None:
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
        )
        await PurchaseService.apply_zero_cost_purchase(
            session,
            purchase_id=purchase_id,
            user_id=snapshot.user_id,
            now_utc=now_utc,
        )


async def validate_precheckout(
    *,
    telegram_user: User,
    invoice_payload: str,
    total_amount: int,
) -> None:
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
        )
        await PurchaseService.validate_precheckout(
            session,
            user_id=snapshot.user_id,
            invoice_payload=invoice_payload,
            total_amount=total_amount,
        )


async def apply_successful_payment(
    *,
    telegram_user: User,
    payment: SuccessfulPayment,
    now_utc: datetime,
):
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
        )
        credit_result = await PurchaseService.apply_successful_payment(
            session,
            user_id=snapshot.user_id,
            invoice_payload=payment.invoice_payload,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            raw_successful_payment=payment.model_dump(exclude_none=True),
            now_utc=now_utc,
        )
        purchase = await PurchaseService.get_by_id(session, credit_result.purchase_id)
        if purchase is not None:
            offer_impression_id = extract_offer_impression_id_from_purchase_idempotency_key(
                purchase.idempotency_key
            )
            if offer_impression_id is not None:
                await OfferService.mark_offer_converted_purchase(
                    session,
                    user_id=snapshot.user_id,
                    impression_id=offer_impression_id,
                    purchase_id=credit_result.purchase_id,
                )
        return credit_result
