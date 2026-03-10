from __future__ import annotations

from uuid import uuid4

from app.bot.keyboards.promo import build_promo_discount_keyboard


def test_build_promo_discount_keyboard_for_specific_product_scope() -> None:
    redemption_id = uuid4()
    keyboard = build_promo_discount_keyboard(
        redemption_id=redemption_id,
        target_scope="PREMIUM_MONTH",
        discount_percent=50,
    )

    assert keyboard is not None
    assert len(keyboard.inline_keyboard) == 2
    button = keyboard.inline_keyboard[0][0]
    assert button.callback_data == f"buy:PREMIUM_MONTH:promo:{redemption_id.hex}"
    assert button.text == "Premium Monat (50⭐)"
    back_button = keyboard.inline_keyboard[1][0]
    assert back_button.callback_data == "home:open"


def test_build_promo_discount_keyboard_for_unknown_scope_returns_none() -> None:
    keyboard = build_promo_discount_keyboard(
        redemption_id=uuid4(),
        target_scope="UNKNOWN_SCOPE",
        discount_percent=10,
    )

    assert keyboard is None


def test_build_promo_discount_keyboard_skips_soft_disabled_products() -> None:
    keyboard = build_promo_discount_keyboard(
        redemption_id=uuid4(),
        target_scope="PREMIUM_ANY",
        discount_percent=10,
    )

    assert keyboard is not None
    rows = keyboard.inline_keyboard
    assert len(rows) == 3
    texts = [row[0].text for row in rows[:-1]]
    assert texts == ["Premium Start (27⭐)", "Premium Monat (90⭐)"]
