from __future__ import annotations

import hashlib
from datetime import datetime

import structlog
from aiogram.types import RefundedPayment, SuccessfulPayment, User

from app.bot.handlers.payments_helpers import (
    extract_offer_impression_id_from_purchase_idempotency_key,
)
from app.db.session import SessionLocal
from app.economy.offers.service import OfferService
from app.economy.purchases.errors import PurchaseNotFoundError, PurchaseRefundValidationError
from app.economy.purchases.service import PurchaseService
from app.services.user_onboarding import UserOnboardingService

logger = structlog.get_logger(__name__)


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
    precheckout_query_id: str,
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
            precheckout_query_id=precheckout_query_id,
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


async def refund_payment_update(
    *,
    telegram_user: User,
    refunded_payment: RefundedPayment,
    now_utc: datetime,
):
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
        )
        purchase = await PurchaseService.get_by_telegram_payment_charge_id_for_update(
            session,
            refunded_payment.telegram_payment_charge_id,
        )
        if purchase is None:
            purchase = await PurchaseService.get_by_invoice_payload_for_update(
                session,
                refunded_payment.invoice_payload,
            )
        if purchase is None:
            raise PurchaseNotFoundError
        if (
            purchase.user_id != snapshot.user_id
            or purchase.invoice_payload != refunded_payment.invoice_payload
        ):
            raise PurchaseRefundValidationError
        _validate_refunded_payment_matches_purchase(
            purchase=purchase,
            refunded_payment=refunded_payment,
        )
        existing_charge_id = getattr(purchase, "telegram_payment_charge_id", None)
        if existing_charge_id not in (
            None,
            refunded_payment.telegram_payment_charge_id,
        ):
            raise PurchaseRefundValidationError
        _mark_refunded_payment_evidence(
            purchase=purchase,
            telegram_payment_charge_id=refunded_payment.telegram_payment_charge_id,
            now_utc=now_utc,
        )
        return await PurchaseService.refund_purchase(
            session,
            purchase_id=purchase.id,
            now_utc=now_utc,
            provider_refund_confirmed=True,
        )


def _validate_refunded_payment_matches_purchase(
    *,
    purchase,
    refunded_payment: RefundedPayment,
) -> None:
    if purchase.currency != refunded_payment.currency:
        _log_refund_validation_rejected(
            purchase=purchase,
            refunded_payment=refunded_payment,
            reason="currency_mismatch",
        )
        raise PurchaseRefundValidationError
    if purchase.stars_amount != refunded_payment.total_amount:
        _log_refund_validation_rejected(
            purchase=purchase,
            refunded_payment=refunded_payment,
            reason="amount_mismatch",
        )
        raise PurchaseRefundValidationError


def _log_refund_validation_rejected(
    *,
    purchase,
    refunded_payment: RefundedPayment,
    reason: str,
) -> None:
    logger.warning(
        "payment_refund_update_validation_rejected",
        purchase_id=str(purchase.id),
        reason=reason,
        expected_currency=purchase.currency,
        refunded_currency=refunded_payment.currency,
        expected_total_amount=purchase.stars_amount,
        refunded_total_amount=refunded_payment.total_amount,
        telegram_payment_charge_id_hash=_payment_identifier_hash(
            refunded_payment.telegram_payment_charge_id
        ),
    )


def _payment_identifier_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _mark_refunded_payment_evidence(
    *,
    purchase,
    telegram_payment_charge_id: str,
    now_utc: datetime,
) -> None:
    purchase.telegram_payment_charge_id = telegram_payment_charge_id
    status = getattr(purchase, "status", None)
    if status in {"CREATED", "INVOICE_SENT", "PRECHECKOUT_OK"}:
        purchase.status = "PAID_UNCREDITED"
        status = "PAID_UNCREDITED"
    if status == "PAID_UNCREDITED" and getattr(purchase, "paid_at", None) is None:
        purchase.paid_at = now_utc
