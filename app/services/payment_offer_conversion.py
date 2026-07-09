from __future__ import annotations

from app.bot.handlers.payments_helpers import (
    extract_offer_impression_id_from_purchase_idempotency_key,
)
from app.economy.offers.service import OfferService
from app.economy.purchases.service import PurchaseService


async def mark_payment_offer_conversion(
    session,
    *,
    user_id: int,
    purchase_id,
) -> None:
    purchase = await PurchaseService.get_by_id(session, purchase_id)
    if purchase is None:
        return
    offer_impression_id = extract_offer_impression_id_from_purchase_idempotency_key(
        purchase.idempotency_key
    )
    if offer_impression_id is None:
        return
    await OfferService.mark_offer_converted_purchase(
        session,
        user_id=user_id,
        impression_id=offer_impression_id,
        purchase_id=purchase_id,
    )
