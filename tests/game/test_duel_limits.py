from __future__ import annotations

import pytest

from app.economy.purchases.catalog import is_product_available_for_sale
from app.game.duels.constants import (
    DUEL_FREE_LIMITS_PER_DAY,
    DUEL_LIMIT_ACTION_ARENA_ACCEPT,
    DUEL_LIMIT_ACTION_ARENA_CREATE,
    DUEL_LIMIT_ACTION_FRIEND_CREATE,
    DUEL_LIMIT_ACTION_REVANCHE,
    DUEL_PAYWALL_PRODUCT_CODES,
    DUEL_PREMIUM_REWARD_ONLY_PRODUCT_CODE,
)
from app.game.duels.limits import (
    DUEL_ACCESS_FREE,
    DUEL_ACCESS_PAID_TICKET,
    DUEL_ACCESS_PREMIUM,
    DuelLimitService,
)
from app.game.sessions.errors import DuelLimitRequiredError


def test_duel_free_limits_match_product_contract() -> None:
    assert DUEL_FREE_LIMITS_PER_DAY == {
        DUEL_LIMIT_ACTION_ARENA_ACCEPT: 3,
        DUEL_LIMIT_ACTION_ARENA_CREATE: 1,
        DUEL_LIMIT_ACTION_FRIEND_CREATE: 2,
        DUEL_LIMIT_ACTION_REVANCHE: 1,
    }


def test_duel_paywall_products_are_only_ticket_and_premium_week() -> None:
    products = DuelLimitService.paywall_products()

    assert tuple(product.product_code for product in products) == DUEL_PAYWALL_PRODUCT_CODES
    assert DUEL_PAYWALL_PRODUCT_CODES == ("FRIEND_CHALLENGE_5", "PREMIUM_WEEK")
    assert DUEL_PREMIUM_REWARD_ONLY_PRODUCT_CODE not in DUEL_PAYWALL_PRODUCT_CODES
    assert not is_product_available_for_sale(DUEL_PREMIUM_REWARD_ONLY_PRODUCT_CODE)


@pytest.mark.parametrize(
    (
        "premium_active",
        "free_used_today",
        "paid_ticket_uses",
        "credited_tickets",
        "expected_allowed",
        "expected_access_type",
    ),
    [
        (True, 99, 99, 0, True, DUEL_ACCESS_PREMIUM),
        (False, 1, 0, 0, True, DUEL_ACCESS_FREE),
        (False, 2, 0, 1, True, DUEL_ACCESS_PAID_TICKET),
        (False, 2, 1, 1, False, None),
    ],
)
def test_resolve_access_type_uses_premium_free_quota_then_ticket(
    premium_active: bool,
    free_used_today: int,
    paid_ticket_uses: int,
    credited_tickets: int,
    expected_allowed: bool,
    expected_access_type: str | None,
) -> None:
    decision = DuelLimitService.resolve_access_type(
        action=DUEL_LIMIT_ACTION_FRIEND_CREATE,
        premium_active=premium_active,
        free_used_today=free_used_today,
        paid_ticket_uses=paid_ticket_uses,
        credited_tickets=credited_tickets,
    )

    assert decision.allowed is expected_allowed
    assert decision.access_type == expected_access_type
    assert decision.paywall_product_codes == DUEL_PAYWALL_PRODUCT_CODES


def test_arena_start_requires_duel_limit_gate() -> None:
    with pytest.raises(DuelLimitRequiredError):
        DuelLimitService.assert_start_gate("ARENA_DUEL", duel_limit_checked=False)

    DuelLimitService.assert_start_gate("ARENA_DUEL", duel_limit_checked=True)
    DuelLimitService.assert_start_gate("MENU", duel_limit_checked=False)
