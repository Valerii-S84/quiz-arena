from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.economy.purchases.catalog import get_product
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


def _parse_buy_callback_data(callback_data: str) -> tuple[str, UUID | None]:
    parts = callback_data.split(":")
    if len(parts) == 2:
        return parts[1], None
    if len(parts) == 4 and parts[2] == "promo":
        return parts[1], UUID(parts[3])
    raise ValueError("invalid buy callback")


@router.callback_query(F.data.startswith("buy:"))
async def handle_buy(callback: CallbackQuery) -> None:
    if callback.data is None or callback.from_user is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    try:
        product_code, promo_redemption_id = _parse_buy_callback_data(callback.data)
    except ValueError:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    product = get_product(product_code)
    if product is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    try:
        async with SessionLocal.begin() as session:
            snapshot = await UserOnboardingService.ensure_home_snapshot(
                session,
                telegram_user=callback.from_user,
            )
            init_result = await PurchaseService.init_purchase(
                session,
                user_id=snapshot.user_id,
                product_code=product_code,
                idempotency_key=f"buy:{product_code}:{callback.id}",
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
        async with SessionLocal.begin() as session:
            snapshot = await UserOnboardingService.ensure_home_snapshot(
                session,
                telegram_user=pre_checkout_query.from_user,
            )
            await PurchaseService.validate_precheckout(
                session,
                user_id=snapshot.user_id,
                invoice_payload=pre_checkout_query.invoice_payload,
                total_amount=pre_checkout_query.total_amount,
            )
    except PurchasePrecheckoutValidationError:
        await pre_checkout_query.answer(ok=False, error_message=TEXTS_DE["msg.purchase.error.failed"])
        return
    except ProductNotFoundError:
        await pre_checkout_query.answer(ok=False, error_message=TEXTS_DE["msg.purchase.error.failed"])
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
        async with SessionLocal.begin() as session:
            snapshot = await UserOnboardingService.ensure_home_snapshot(
                session,
                telegram_user=message.from_user,
            )
            credit_result = await PurchaseService.apply_successful_payment(
                session,
                user_id=snapshot.user_id,
                invoice_payload=payment.invoice_payload,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
                raw_successful_payment=payment.model_dump(exclude_none=True),
                now_utc=now_utc,
            )
    except (PurchaseNotFoundError, ProductNotFoundError, PurchasePrecheckoutValidationError):
        await message.answer(TEXTS_DE["msg.purchase.error.failed"], reply_markup=build_home_keyboard())
        return

    text_key = {
        "ENERGY_10": "msg.purchase.success.energy10",
        "MEGA_PACK_15": "msg.purchase.success.megapack",
        "STREAK_SAVER_20": "msg.purchase.success.streaksaver",
        "PREMIUM_STARTER": "msg.purchase.success.premium",
        "PREMIUM_MONTH": "msg.purchase.success.premium",
        "PREMIUM_SEASON": "msg.purchase.success.premium",
        "PREMIUM_YEAR": "msg.purchase.success.premium",
    }.get(credit_result.product_code, "msg.purchase.success.energy10")

    await message.answer(TEXTS_DE[text_key], reply_markup=build_home_keyboard())
