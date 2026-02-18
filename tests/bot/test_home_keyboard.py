from app.bot.keyboards.home import build_home_keyboard


def test_home_keyboard_contains_promo_button() -> None:
    keyboard = build_home_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.callback_data == "promo:open" for button in buttons)
