from __future__ import annotations

from .builder import _as_init_result, _build_purchase
from .constants import (
    PREMIUM_PLAN_RANKS,
    PROMO_RESERVATION_TTL,
    STREAK_SAVER_PURCHASE_LOCK_WINDOW,
)
from .credit import apply_successful_payment
from .entitlements import _apply_premium_entitlement
from .events import _emit_purchase_event
from .init import init_purchase
from .precheckout import mark_invoice_sent, validate_precheckout
from .utilities import (
    _build_invoice_payload,
    _calculate_discount_amount,
    _is_promo_scope_applicable,
    _premium_plan_rank,
)
from .validation import (
    _validate_and_reserve_discount_redemption,
    _validate_reserved_discount_for_purchase,
    _validate_streak_saver_purchase_limit,
)


class PurchaseService:
    _emit_purchase_event = staticmethod(_emit_purchase_event)
    _build_invoice_payload = staticmethod(_build_invoice_payload)
    _premium_plan_rank = staticmethod(_premium_plan_rank)
    _calculate_discount_amount = staticmethod(_calculate_discount_amount)
    _is_promo_scope_applicable = staticmethod(_is_promo_scope_applicable)
    _build_purchase = staticmethod(_build_purchase)
    _as_init_result = staticmethod(_as_init_result)
    _validate_streak_saver_purchase_limit = staticmethod(_validate_streak_saver_purchase_limit)
    _validate_and_reserve_discount_redemption = staticmethod(
        _validate_and_reserve_discount_redemption
    )
    _validate_reserved_discount_for_purchase = staticmethod(
        _validate_reserved_discount_for_purchase
    )
    _apply_premium_entitlement = staticmethod(_apply_premium_entitlement)
    init_purchase = staticmethod(init_purchase)
    mark_invoice_sent = staticmethod(mark_invoice_sent)
    validate_precheckout = staticmethod(validate_precheckout)
    apply_successful_payment = staticmethod(apply_successful_payment)


__all__ = [
    "PREMIUM_PLAN_RANKS",
    "PROMO_RESERVATION_TTL",
    "STREAK_SAVER_PURCHASE_LOCK_WINDOW",
    "PurchaseService",
]
