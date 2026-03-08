from __future__ import annotations

from datetime import datetime, timezone

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from app.bot.handlers.payments_helpers import (
    build_purchase_idempotency_key,
    extract_offer_impression_id_from_purchase_idempotency_key,
    parse_buy_callback_data,
    success_text_key,
)
from app.bot.handlers.payments_runtime import (
    apply_successful_payment,
    apply_zero_cost_purchase,
    validate_precheckout,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.economy.offers.service import OfferService
from app.economy.purchases.catalog import get_product, is_product_available_for_sale
from app.economy.purchases.errors import (
    PremiumDowngradeNotAllowedError,
    ProductNotFoundError,
    PurchaseInitValidationError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
    StreakSaverPurchaseLimitError,
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


@router.callback_query(F.data.startswith("buy:"))
async def handle_buy(callback: CallbackQuery) -> None:
    if callback.data is None or callback.from_user is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    try:
        product_code, promo_redemption_id, offer_impression_id = parse_buy_callback_data(
            callback.data
        )
    except ValueError:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    product = get_product(product_code)
    if product is None or not is_product_available_for_sale(product_code):
        await callback.answer(TEXTS_DE["msg.purchase.error.failed"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    try:
        async with SessionLocal.begin() as session:
            snapshot = await UserOnboardingService.ensure_home_snapshot(
                session,
                telegram_user=callback.from_user,
            )
            if offer_impression_id is not None:
                await OfferService.mark_offer_clicked(
                    session,
                    user_id=snapshot.user_id,
                    impression_id=offer_impression_id,
                    clicked_at=now_utc,
                )
            init_result = await PurchaseService.init_purchase(
                session,
                user_id=snapshot.user_id,
                product_code=product_code,
                idempotency_key=build_purchase_idempotency_key(
                    product_code=product_code,
                    callback_id=callback.id,
                    offer_impression_id=offer_impression_id,
                ),
                now_utc=now_utc,
                promo_redemption_id=promo_redemption_id,
            )
    except PremiumDowngradeNotAllowedError:
        await callback.answer(TEXTS_DE["msg.premium.downgrade.blocked"], show_alert=True)
        return
    except StreakSaverPurchaseLimitError:
        await callback.answer(TEXTS_DE["msg.purchase.error.streaksaver.limit"], show_alert=True)
        return
    except (ProductNotFoundError, PurchaseInitValidationError):
        await callback.answer(TEXTS_DE["msg.purchase.error.failed"], show_alert=True)
        return

    if init_result.final_stars_amount == 0:
        try:
            await apply_zero_cost_purchase(
                telegram_user=callback.from_user,
                purchase_id=init_result.purchase_id,
                now_utc=now_utc,
            )
        except (
            PurchaseNotFoundError,
            ProductNotFoundError,
            PurchasePrecheckoutValidationError,
        ):
            await callback.answer(TEXTS_DE["msg.purchase.error.failed"], show_alert=True)
            return

        if callback.message is not None:
            await callback.message.answer(
                TEXTS_DE[success_text_key(product_code)],
                reply_markup=build_home_keyboard(),
            )
        await callback.answer()
        return

    try:
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=product.title,
            description=product.description,
            payload=init_result.invoice_payload,
            currency="XTR",
            prices=[LabeledPrice(label=product.title, amount=init_result.final_stars_amount)],
            provider_token=None,
        )
    except Exception as exc:
        logger.exception(
            "telegram_send_invoice_failed",
            user_id=callback.from_user.id,
            purchase_id=str(init_result.purchase_id),
            product_code=product_code,
            error_type=type(exc).__name__,
        )
        await callback.answer(TEXTS_DE["msg.purchase.error.failed"], show_alert=True)
        return

    async with SessionLocal.begin() as session:
        await PurchaseService.mark_invoice_sent(
            session,
            purchase_id=init_result.purchase_id,
        )

    await callback.answer()


@router.pre_checkout_query()
async def handle_precheckout(pre_checkout_query: PreCheckoutQuery) -> None:
    try:
        await validate_precheckout(
            telegram_user=pre_checkout_query.from_user,
            invoice_payload=pre_checkout_query.invoice_payload,
            total_amount=pre_checkout_query.total_amount,
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
    ):
        await message.answer(
            TEXTS_DE["msg.purchase.error.failed"], reply_markup=build_home_keyboard()
        )
        return

    await message.answer(
        TEXTS_DE[success_text_key(credit_result.product_code)],
        reply_markup=build_home_keyboard(),
    )
