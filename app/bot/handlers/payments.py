from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from app.bot.handlers.payments_buy_flow import BuyHandlerServices, handle_buy_callback
from app.bot.handlers.payments_duel_paywall import (
    _duel_paywall_context_from_callback as _duel_paywall_context_from_callback,
)
from app.bot.handlers.payments_duel_paywall import _emit_duel_paywall_click
from app.bot.handlers.payments_duel_paywall import (
    _is_duel_paywall_callback as _is_duel_paywall_callback,
)
from app.bot.handlers.payments_helpers import (
    build_purchase_idempotency_key,
    extract_offer_impression_id_from_purchase_idempotency_key,
    parse_buy_callback_data,
    success_text_key,
)
from app.bot.handlers.payments_runtime import (
    apply_successful_payment,
    apply_zero_cost_purchase,
    refund_payment_update,
    validate_precheckout,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.economy.offers.service import OfferService
from app.economy.purchases.catalog import get_product, is_product_available_for_sale
from app.economy.purchases.errors import (
    ProductNotFoundError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
    PurchaseRefundInvariantError,
    PurchaseRefundValidationError,
)
from app.economy.purchases.service import PurchaseService
from app.services.user_onboarding import UserOnboardingService

router = Router(name="payments")
logger = structlog.get_logger(__name__)
_build_purchase_idempotency_key = build_purchase_idempotency_key
_extract_offer_impression_id_from_purchase_idempotency_key = (
    extract_offer_impression_id_from_purchase_idempotency_key
)
_parse_buy_callback_data = parse_buy_callback_data
_success_text_key = success_text_key


def _invoice_payload_hash(invoice_payload: str) -> str:
    return hashlib.sha256(invoice_payload.encode("utf-8")).hexdigest()[:16]


@router.callback_query(F.data.startswith("buy:"))
async def handle_buy(callback: CallbackQuery) -> None:
    await handle_buy_callback(
        callback=callback,
        services=BuyHandlerServices(
            parse_buy_callback_data_fn=parse_buy_callback_data,
            get_product_fn=get_product,
            is_product_available_for_sale_fn=is_product_available_for_sale,
            session_local=SessionLocal,
            user_onboarding_service=UserOnboardingService,
            offer_service=OfferService,
            purchase_service=PurchaseService,
            emit_duel_paywall_click_fn=_emit_duel_paywall_click,
            build_purchase_idempotency_key_fn=build_purchase_idempotency_key,
            apply_zero_cost_purchase_fn=apply_zero_cost_purchase,
            success_text_key_fn=success_text_key,
            logger=logger,
        ),
    )


@router.pre_checkout_query()
async def handle_precheckout(pre_checkout_query: PreCheckoutQuery) -> None:
    try:
        await validate_precheckout(
            telegram_user=pre_checkout_query.from_user,
            invoice_payload=pre_checkout_query.invoice_payload,
            total_amount=pre_checkout_query.total_amount,
            precheckout_query_id=pre_checkout_query.id,
        )
    except (PurchasePrecheckoutValidationError, ProductNotFoundError):
        await pre_checkout_query.answer(
            ok=False, error_message=TEXTS_DE["msg.purchase.error.failed"]
        )
        return

    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message) -> None:
    if message.from_user is None or message.successful_payment is None:
        await message.answer(TEXTS_DE["msg.system.error"])
        return

    payment = message.successful_payment
    now_utc = datetime.now(timezone.utc)
    invoice_payload_hash = _invoice_payload_hash(payment.invoice_payload)

    logger.info(
        "payment_successful_update_received",
        telegram_user_id=message.from_user.id,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
        invoice_payload_hash=invoice_payload_hash,
        currency=getattr(payment, "currency", None),
        total_amount=getattr(payment, "total_amount", None),
    )

    try:
        credit_result = await apply_successful_payment(
            telegram_user=message.from_user,
            payment=payment,
            now_utc=now_utc,
        )
    except (
        PurchaseNotFoundError,
        ProductNotFoundError,
        PurchasePrecheckoutValidationError,
    ) as exc:
        logger.warning(
            "payment_credit_failed",
            telegram_user_id=message.from_user.id,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            invoice_payload_hash=invoice_payload_hash,
            error_type=type(exc).__name__,
        )
        await message.answer(
            TEXTS_DE["msg.purchase.error.failed"], reply_markup=build_home_keyboard()
        )
        return

    await message.answer(
        TEXTS_DE[success_text_key(credit_result.product_code)],
        reply_markup=build_home_keyboard(),
    )


@router.message(F.refunded_payment)
async def handle_refunded_payment(message: Message) -> None:
    if message.from_user is None or message.refunded_payment is None:
        await message.answer(TEXTS_DE["msg.system.error"])
        return

    refunded_payment = message.refunded_payment
    now_utc = datetime.now(timezone.utc)
    invoice_payload_hash = _invoice_payload_hash(refunded_payment.invoice_payload)

    logger.info(
        "payment_refunded_update_received",
        telegram_user_id=message.from_user.id,
        telegram_payment_charge_id=refunded_payment.telegram_payment_charge_id,
        invoice_payload_hash=invoice_payload_hash,
        currency=getattr(refunded_payment, "currency", None),
        total_amount=getattr(refunded_payment, "total_amount", None),
    )

    try:
        await refund_payment_update(
            telegram_user=message.from_user,
            refunded_payment=refunded_payment,
            now_utc=now_utc,
        )
    except (
        PurchaseNotFoundError,
        PurchaseRefundValidationError,
        PurchaseRefundInvariantError,
    ) as exc:
        logger.warning(
            "payment_refund_update_failed",
            telegram_user_id=message.from_user.id,
            telegram_payment_charge_id=refunded_payment.telegram_payment_charge_id,
            invoice_payload_hash=invoice_payload_hash,
            error_type=type(exc).__name__,
        )
        raise
