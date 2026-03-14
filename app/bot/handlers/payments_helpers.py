from __future__ import annotations

import hashlib
from uuid import UUID


def _token_hash(value: str, *, length: int) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def build_purchase_idempotency_key(
    *,
    product_code: str,
    callback_id: str,
    offer_impression_id: int | None,
) -> str:
    product_token = _token_hash(product_code, length=8)
    callback_token = _token_hash(callback_id, length=10)
    if offer_impression_id is not None:
        return f"buy:{product_token}:offer:{offer_impression_id}:{callback_token}"
    return f"buy:{product_token}:{callback_token}"


def extract_offer_impression_id_from_purchase_idempotency_key(
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


def parse_buy_callback_data(callback_data: str) -> tuple[str, UUID | None, int | None]:
    parts = callback_data.split(":")
    if len(parts) == 2:
        return parts[1], None, None
    if len(parts) == 4 and parts[2] == "promo":
        return parts[1], UUID(parts[3]), None
    if len(parts) == 4 and parts[2] == "offer":
        return parts[1], None, int(parts[3])
    raise ValueError("invalid buy callback")


def success_text_key(product_code: str) -> str:
    return {
        "ENERGY_10": "msg.purchase.success.energy10",
        "FRIEND_CHALLENGE_5": "msg.purchase.success.friend_challenge_ticket",
        "STREAK_SAVER_20": "msg.purchase.success.streaksaver",
        "PREMIUM_STARTER": "msg.purchase.success.premium",
        "PREMIUM_MONTH": "msg.purchase.success.premium",
        "PREMIUM_SEASON": "msg.purchase.success.premium",
        "PREMIUM_YEAR": "msg.purchase.success.premium",
    }.get(product_code, "msg.purchase.success.energy10")
