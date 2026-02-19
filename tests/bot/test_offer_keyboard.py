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
