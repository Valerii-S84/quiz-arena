from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from aiogram.types import CallbackQuery, LabeledPrice

from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.economy.purchases.errors import (
    ProductNotFoundError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
)


async def apply_zero_cost_purchase_and_notify(
    *,
    callback: CallbackQuery,
    product_code: str,
    purchase_id: Any,
    now_utc: datetime,
    apply_zero_cost_purchase_fn: Callable[..., Any],
    success_text_key_fn: Callable[[str], str],
) -> bool:
    try:
        await apply_zero_cost_purchase_fn(
            telegram_user=callback.from_user,
            purchase_id=purchase_id,
            now_utc=now_utc,
        )
    except (
        PurchaseNotFoundError,
        ProductNotFoundError,
        PurchasePrecheckoutValidationError,
    ):
        await callback.answer(TEXTS_DE["msg.purchase.error.failed"], show_alert=True)
        return False

    if callback.message is not None:
        await callback.message.answer(
            TEXTS_DE[success_text_key_fn(product_code)],
            reply_markup=build_home_keyboard(),
        )
    await callback.answer()
    return True


async def send_purchase_invoice(
    *,
    callback: CallbackQuery,
    product: Any,
    init_result: Any,
    product_code: str,
    logger: Any,
) -> bool:
    if callback.bot is None:
        return False
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
        return False
    return True


async def send_purchase_invoice_and_mark_sent(
    *,
    callback: CallbackQuery,
    product: Any,
    init_result: Any,
    product_code: str,
    session_local: Any,
    purchase_service: Any,
    logger: Any,
) -> bool:
    invoice_sent = await send_purchase_invoice(
        callback=callback,
        product=product,
        init_result=init_result,
        product_code=product_code,
        logger=logger,
    )
    if not invoice_sent:
        return False
    async with session_local.begin() as session:
        await purchase_service.mark_invoice_sent(
            session,
            purchase_id=init_result.purchase_id,
        )
    return True
