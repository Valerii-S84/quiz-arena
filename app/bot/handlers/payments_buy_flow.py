from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aiogram.types import CallbackQuery

from app.bot.handlers.payments_buy import (
    BuyProductUnavailableError,
    BuyPurchaseRequest,
    BuyPurchaseServices,
    init_buy_purchase,
    select_buy_product,
)
from app.bot.handlers.payments_buy_completion import (
    apply_zero_cost_purchase_and_notify,
    send_purchase_invoice_and_mark_sent,
)
from app.bot.texts.de import TEXTS_DE
from app.economy.purchases.errors import (
    PremiumDowngradeNotAllowedError,
    ProductNotFoundError,
    PurchaseInitValidationError,
    StreakSaverPurchaseLimitError,
)


@dataclass(frozen=True, slots=True)
class BuyHandlerServices:
    parse_buy_callback_data_fn: Callable[..., tuple[str, Any, int | None]]
    get_product_fn: Callable[[str], Any]
    is_product_available_for_sale_fn: Callable[[str], bool]
    session_local: Any
    user_onboarding_service: Any
    offer_service: Any
    purchase_service: Any
    emit_duel_paywall_click_fn: Callable[..., Any]
    build_purchase_idempotency_key_fn: Callable[..., str]
    apply_zero_cost_purchase_fn: Callable[..., Any]
    success_text_key_fn: Callable[[str], str]
    logger: Any


async def handle_buy_callback(
    callback: CallbackQuery,
    *,
    services: BuyHandlerServices,
) -> None:
    if callback.data is None or callback.from_user is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    try:
        selection = select_buy_product(
            callback_data=callback.data,
            parse_buy_callback_data_fn=services.parse_buy_callback_data_fn,
            get_product_fn=services.get_product_fn,
            is_product_available_for_sale_fn=services.is_product_available_for_sale_fn,
        )
    except ValueError:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    except BuyProductUnavailableError:
        await callback.answer(TEXTS_DE["msg.purchase.error.failed"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    init_result = await _init_or_answer_failure(
        callback=callback,
        selection=selection,
        now_utc=now_utc,
        services=services,
    )
    if init_result is None:
        return
    await _complete_initialized_purchase(
        callback=callback,
        selection=selection,
        init_result=init_result,
        now_utc=now_utc,
        services=services,
    )


async def _init_or_answer_failure(
    *,
    callback: CallbackQuery,
    selection: Any,
    now_utc: datetime,
    services: BuyHandlerServices,
) -> Any | None:
    try:
        return await init_buy_purchase(
            request=BuyPurchaseRequest(
                callback=callback,
                product_code=selection.product_code,
                promo_redemption_id=selection.promo_redemption_id,
                offer_impression_id=selection.offer_impression_id,
                now_utc=now_utc,
            ),
            services=BuyPurchaseServices(
                session_local=services.session_local,
                user_onboarding_service=services.user_onboarding_service,
                offer_service=services.offer_service,
                purchase_service=services.purchase_service,
                emit_duel_paywall_click_fn=services.emit_duel_paywall_click_fn,
                build_purchase_idempotency_key_fn=services.build_purchase_idempotency_key_fn,
            ),
        )
    except PremiumDowngradeNotAllowedError:
        await callback.answer(TEXTS_DE["msg.premium.downgrade.blocked"], show_alert=True)
    except StreakSaverPurchaseLimitError:
        await callback.answer(TEXTS_DE["msg.purchase.error.streaksaver.limit"], show_alert=True)
    except (ProductNotFoundError, PurchaseInitValidationError):
        await callback.answer(TEXTS_DE["msg.purchase.error.failed"], show_alert=True)
    return None


async def _complete_initialized_purchase(
    *,
    callback: CallbackQuery,
    selection: Any,
    init_result: Any,
    now_utc: datetime,
    services: BuyHandlerServices,
) -> None:
    if init_result.final_stars_amount == 0:
        await apply_zero_cost_purchase_and_notify(
            callback=callback,
            product_code=selection.product_code,
            purchase_id=init_result.purchase_id,
            now_utc=now_utc,
            apply_zero_cost_purchase_fn=services.apply_zero_cost_purchase_fn,
            success_text_key_fn=services.success_text_key_fn,
        )
        return

    invoice_sent = await send_purchase_invoice_and_mark_sent(
        callback=callback,
        product=selection.product,
        init_result=init_result,
        product_code=selection.product_code,
        session_local=services.session_local,
        purchase_service=services.purchase_service,
        logger=services.logger,
    )
    if not invoice_sent:
        await callback.answer(TEXTS_DE["msg.purchase.error.failed"], show_alert=True)
        return
    await callback.answer()
