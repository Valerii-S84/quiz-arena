from __future__ import annotations

from app.economy.offers.service import OfferService
from app.economy.purchases.service import PurchaseService


def _extract_offer_impression_id_from_purchase_idempotency_key(
    idempotency_key: str,
) -> int | None:
    parts = idempotency_key.split(":")
    if len(parts) != 5:
        return None
    if parts[0] != "buy" or parts[2] != "offer":
        return None
    try:
        return int(parts[3])
    except ValueError:
        return None


async def mark_payment_offer_conversion(
    session,
    *,
    user_id: int,
    purchase_id,
) -> None:
    purchase = await PurchaseService.get_by_id(session, purchase_id)
    if purchase is None:
        return
    offer_impression_id = _extract_offer_impression_id_from_purchase_idempotency_key(
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
