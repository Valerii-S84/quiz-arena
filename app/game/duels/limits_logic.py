from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.game.duels.constants import DUEL_FREE_LIMITS_PER_DAY, DUEL_PAYWALL_PRODUCT_CODES
from app.game.modes.rules import requires_duel_limit_gate

if TYPE_CHECKING:
    from app.economy.purchases.catalog import ProductSpec

DUEL_ACCESS_FREE = "FREE"
DUEL_ACCESS_PAID_TICKET = "PAID_TICKET"
DUEL_ACCESS_PREMIUM = "PREMIUM"
DUEL_ACCESS_TYPES = frozenset({DUEL_ACCESS_FREE, DUEL_ACCESS_PAID_TICKET, DUEL_ACCESS_PREMIUM})
_BERLIN_TZ = ZoneInfo("Europe/Berlin")


@dataclass(frozen=True, slots=True)
class DuelLimitDecision:
    allowed: bool
    access_type: str | None
    free_limit: int
    free_used_today: int
    paid_ticket_uses: int
    credited_tickets: int
    premium_active: bool
    paywall_product_codes: tuple[str, str] = DUEL_PAYWALL_PRODUCT_CODES


def free_limit_for_action(action: str) -> int:
    return DUEL_FREE_LIMITS_PER_DAY[action]


def paywall_product_codes() -> tuple[str, str]:
    return DUEL_PAYWALL_PRODUCT_CODES


def paywall_products() -> tuple[ProductSpec, ...]:
    from app.economy.purchases.catalog import get_product, is_product_available_for_sale

    products: list[ProductSpec] = []
    for product_code in DUEL_PAYWALL_PRODUCT_CODES:
        product = get_product(product_code)
        if product is None or not is_product_available_for_sale(product_code):
            raise RuntimeError(f"duel paywall product is not saleable: {product_code}")
        products.append(product)
    return tuple(products)


def assert_start_gate(source: str, *, duel_limit_checked: bool) -> None:
    if requires_duel_limit_gate(source) and not duel_limit_checked:
        from app.game.sessions.errors import DuelLimitRequiredError

        raise DuelLimitRequiredError


def assert_resolved_access_type(source: str, *, access_type: str) -> None:
    assert_start_gate(
        source,
        duel_limit_checked=access_type in DUEL_ACCESS_TYPES,
    )


def resolve_access_type(
    *,
    action: str,
    premium_active: bool,
    free_used_today: int,
    paid_ticket_uses: int,
    credited_tickets: int,
) -> DuelLimitDecision:
    free_limit = free_limit_for_action(action)
    if premium_active:
        return _build_decision(
            allowed=True,
            access_type=DUEL_ACCESS_PREMIUM,
            free_limit=free_limit,
            free_used_today=free_used_today,
            paid_ticket_uses=paid_ticket_uses,
            credited_tickets=credited_tickets,
            premium_active=True,
        )
    if free_used_today < free_limit:
        return _build_decision(
            allowed=True,
            access_type=DUEL_ACCESS_FREE,
            free_limit=free_limit,
            free_used_today=free_used_today,
            paid_ticket_uses=paid_ticket_uses,
            credited_tickets=credited_tickets,
            premium_active=False,
        )
    has_ticket_balance = credited_tickets > paid_ticket_uses
    if has_ticket_balance:
        return _build_decision(
            allowed=True,
            access_type=DUEL_ACCESS_PAID_TICKET,
            free_limit=free_limit,
            free_used_today=free_used_today,
            paid_ticket_uses=paid_ticket_uses,
            credited_tickets=credited_tickets,
            premium_active=False,
        )
    return _build_decision(
        allowed=False,
        access_type=None,
        free_limit=free_limit,
        free_used_today=free_used_today,
        paid_ticket_uses=paid_ticket_uses,
        credited_tickets=credited_tickets,
        premium_active=False,
    )


def berlin_day_start_utc(now_utc: datetime) -> datetime:
    aware_now = now_utc if now_utc.tzinfo is not None else now_utc.replace(tzinfo=timezone.utc)
    berlin_start = aware_now.astimezone(_BERLIN_TZ).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return berlin_start.astimezone(timezone.utc)


def _build_decision(**kwargs) -> DuelLimitDecision:
    return DuelLimitDecision(**kwargs)
