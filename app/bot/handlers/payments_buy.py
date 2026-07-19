from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiogram.types import CallbackQuery

from app.bot.handlers.payments_duel_paywall import (
    _duel_paywall_context_from_callback,
    _is_duel_paywall_callback,
)


class BuyProductUnavailableError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class BuyProductSelection:
    product_code: str
    promo_redemption_id: Any
    offer_impression_id: int | None
    product: Any


def select_buy_product(
    *,
    callback_data: str,
    parse_buy_callback_data_fn: Callable[..., tuple[str, Any, int | None]],
    get_product_fn: Callable[[str], Any],
    is_product_available_for_sale_fn: Callable[[str], bool],
) -> BuyProductSelection:
    product_code, promo_redemption_id, offer_impression_id = parse_buy_callback_data_fn(
        callback_data
    )
    product = get_product_fn(product_code)
    if product is None or not is_product_available_for_sale_fn(product_code):
        raise BuyProductUnavailableError()
    return BuyProductSelection(
        product_code=product_code,
        promo_redemption_id=promo_redemption_id,
        offer_impression_id=offer_impression_id,
        product=product,
    )


@dataclass(frozen=True, slots=True)
class BuyPurchaseRequest:
    callback: CallbackQuery
    product_code: str
    promo_redemption_id: Any
    offer_impression_id: int | None
    now_utc: datetime


@dataclass(frozen=True, slots=True)
class BuyPurchaseServices:
    session_local: Any
    user_onboarding_service: Any
    offer_service: Any
    purchase_service: Any
    emit_duel_paywall_click_fn: Callable[..., Any]
    build_purchase_idempotency_key_fn: Callable[..., str]


async def init_buy_purchase(*, request: BuyPurchaseRequest, services: BuyPurchaseServices) -> Any:
    async with services.session_local.begin() as session:
        snapshot = await services.user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=request.callback.from_user,
        )
        if request.offer_impression_id is not None:
            await services.offer_service.mark_offer_clicked(
                session,
                user_id=snapshot.user_id,
                impression_id=request.offer_impression_id,
                clicked_at=request.now_utc,
            )
        if _is_duel_paywall_callback(
            request.callback.data or "",
            product_code=request.product_code,
        ):
            await services.emit_duel_paywall_click_fn(
                session,
                user_id=snapshot.user_id,
                product_code=request.product_code,
                happened_at=request.now_utc,
                paywall_context=_duel_paywall_context_from_callback(
                    request.callback.data or "",
                    product_code=request.product_code,
                ),
            )
        return await services.purchase_service.init_purchase(
            session,
            user_id=snapshot.user_id,
            product_code=request.product_code,
            idempotency_key=services.build_purchase_idempotency_key_fn(
                product_code=request.product_code,
                callback_id=request.callback.id,
                offer_impression_id=request.offer_impression_id,
            ),
            now_utc=request.now_utc,
            promo_redemption_id=request.promo_redemption_id,
        )
