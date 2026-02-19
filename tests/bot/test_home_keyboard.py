from app.bot.keyboards.home import build_home_keyboard


def test_home_keyboard_contains_referral_button() -> None:
    keyboard = build_home_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.callback_data == "referral:open" for button in buttons)
    assert any(button.callback_data == "friend:challenge:create" for button in buttons)
    assert any(
        button.text == "👥 FREUNDE EINLADEN" and button.callback_data == "friend:challenge:create"
        for button in buttons
    )


def test_home_keyboard_contains_shop_button_without_direct_buy_buttons() -> None:
    keyboard = build_home_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    callbacks = {button.callback_data for button in buttons}

    assert "shop:open" in callbacks
    assert "buy:ENERGY_10" not in callbacks
    assert "buy:MEGA_PACK_15" not in callbacks
    assert "promo:open" not in callbacks
