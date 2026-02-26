from app.bot.keyboards.home import build_home_keyboard


def test_home_keyboard_has_exact_5_buttons_in_canonical_order() -> None:
    keyboard = build_home_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert len(buttons) == 5
    assert [button.text for button in buttons] == [
        "⚡ MIX SPRINT",
        "⚡ DAILY CHALLENGE",
        "🧠 ARTIKEL SPRINT",
        "🥊 DUELL",
        "🛒 SHOP",
    ]
    assert [button.callback_data for button in buttons] == [
        "play",
        "daily_challenge",
        "mode:ARTIKEL_SPRINT",
        "friend:challenge:create",
        "shop:open",
    ]


def test_home_keyboard_contains_shop_button_without_direct_buy_buttons() -> None:
    keyboard = build_home_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    callbacks = {button.callback_data for button in buttons}

    assert "shop:open" in callbacks
    assert "buy:ENERGY_10" not in callbacks
    assert "buy:MEGA_PACK_15" not in callbacks
    assert "promo:open" not in callbacks


def test_home_keyboard_does_not_include_liga_or_removed_modes() -> None:
    keyboard = build_home_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    callbacks = {button.callback_data for button in buttons}
    labels = {button.text for button in buttons}

    assert "liga:open" not in callbacks
    assert all("LIGA" not in label for label in labels)
    assert "daily_challenge" in callbacks
    assert "mode:CASES_PRACTICE" not in callbacks
    assert "referral:open" not in callbacks
