from __future__ import annotations

from datetime import timedelta

from app.economy.offers.constants import (
    BLOCKING_MODAL_COOLDOWN,
    DUEL_TICKET_SECOND_BUY_WINDOW,
    MONETIZATION_IMPRESSIONS_PER_DAY_CAP,
    OFFER_MUTE_WINDOW,
    OFFER_REPEAT_COOLDOWN,
    OFFER_TEMPLATES,
    TRG_DUEL_TICKET_SECOND_BUY,
)


def test_offer_caps_match_default_configuration() -> None:
    assert BLOCKING_MODAL_COOLDOWN == timedelta(hours=6)
    assert MONETIZATION_IMPRESSIONS_PER_DAY_CAP == 3
    assert OFFER_REPEAT_COOLDOWN == timedelta(hours=24)
    assert OFFER_MUTE_WINDOW == timedelta(hours=72)
    assert DUEL_TICKET_SECOND_BUY_WINDOW == timedelta(days=7)


def test_duel_ticket_second_buy_offer_points_to_arena_pass_week() -> None:
    template = OFFER_TEMPLATES[TRG_DUEL_TICKET_SECOND_BUY]

    assert template.offer_code == "OFFER_ARENA_PASS_AFTER_TICKETS"
    assert template.text_key == "msg.offer.arena_pass.after_tickets"
    assert template.cta_product_codes == ("PREMIUM_WEEK",)
    assert template.blocking_modal is True
