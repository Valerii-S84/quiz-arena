from app.bot.keyboards.offers import build_offer_keyboard
from app.economy.offers.types import OfferSelection


def test_offer_keyboard_contains_only_cta_buttons() -> None:
    selection = OfferSelection(
        impression_id=42,
        offer_code="OFFER_ENERGY_ZERO",
        trigger_code="TRG_ENERGY_ZERO",
        priority=100,
        text_key="msg.offer.energy.zero",
        cta_product_codes=("ENERGY_10",),
        idempotent_replay=False,
    )

    keyboard = build_offer_keyboard(selection)
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "buy:ENERGY_10:offer:42" in callbacks
    assert "offer:dismiss:42" not in callbacks


def test_offer_keyboard_skips_unknown_products_only() -> None:
    selection = OfferSelection(
        impression_id=77,
        offer_code="OFFER_ENERGY_ZERO",
        trigger_code="TRG_ENERGY_ZERO",
        priority=100,
        text_key="msg.offer.energy.zero",
        cta_product_codes=("UNKNOWN_PRODUCT", "PREMIUM_SEASON", "PREMIUM_YEAR", "PREMIUM_MONTH"),
        idempotent_replay=False,
    )

    keyboard = build_offer_keyboard(selection)
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert callbacks == [
        "buy:PREMIUM_SEASON:offer:77",
        "buy:PREMIUM_YEAR:offer:77",
        "buy:PREMIUM_MONTH:offer:77",
    ]


def test_offer_keyboard_labels_premium_week_as_arena_pass() -> None:
    selection = OfferSelection(
        impression_id=88,
        offer_code="OFFER_ARENA_PASS_AFTER_TICKETS",
        trigger_code="TRG_DUEL_TICKET_SECOND_BUY",
        priority=88,
        text_key="msg.offer.arena_pass.after_tickets",
        cta_product_codes=("PREMIUM_WEEK",),
        idempotent_replay=False,
    )

    keyboard = build_offer_keyboard(selection)
    button = keyboard.inline_keyboard[0][0]

    assert button.text == "Arena Pass 7 Tage (29⭐)"
    assert button.callback_data == "buy:PREMIUM_WEEK:offer:88"
