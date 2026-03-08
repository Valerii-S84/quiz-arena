from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.bot.promo_labels import get_promo_product_label
from app.economy.energy.constants import BERLIN_TIMEZONE
from app.economy.promo.types import PromoRedeemResult


def format_berlin_time(at_utc: datetime | None) -> str:
    if at_utc is None:
        return "unbekannt"
    return at_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).strftime("%d.%m %H:%M")


def resolve_scope_label(target_scope: str | None, *, applicable_products: list[str] | None) -> str:
    if applicable_products:
        if len(applicable_products) == 1:
            product_label = get_promo_product_label(applicable_products[0])
            if product_label is not None:
                return product_label
        return "ausgewaehlte Produkte"
    if target_scope is None:
        return "deine Auswahl"
    if target_scope == "ANY":
        return "alle Pakete"
    if target_scope == "MICRO_ANY":
        return "Mikro-Pakete"
    if target_scope == "PREMIUM_ANY":
        return "Premium-Plaene"
    product_label = get_promo_product_label(target_scope)
    if product_label is not None:
        return product_label
    return target_scope


def resolve_discount_label(result: PromoRedeemResult) -> str:
    if result.discount_type == "FREE":
        return "kostenlos"
    if result.discount_type == "FIXED":
        return f"{result.discount_value or 0}⭐ Rabatt"
    return f"{result.discount_value or result.discount_percent or 0}% Rabatt"
