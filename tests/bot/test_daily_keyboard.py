from app.bot.keyboards.daily import build_daily_push_keyboard, build_daily_result_keyboard


def test_daily_result_keyboard_has_review_and_home_buttons() -> None:
    keyboard = build_daily_result_keyboard(daily_run_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "daily:result:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert "home:open" in callbacks
    assert "Nochmal anschauen" in labels
    assert "Zum Menü" in labels


def test_daily_push_keyboard_starts_daily_challenge() -> None:
    keyboard = build_daily_push_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert len(buttons) == 1
    assert buttons[0].callback_data == "daily_challenge"
