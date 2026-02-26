from app.bot.keyboards.channel_bonus import build_channel_bonus_keyboard


def test_channel_bonus_keyboard_contains_channel_url_and_check_button() -> None:
    keyboard = build_channel_bonus_keyboard(channel_url="https://t.me/quiz_arena_test")
    first_button = keyboard.inline_keyboard[0][0]
    second_button = keyboard.inline_keyboard[1][0]

    assert first_button.url == "https://t.me/quiz_arena_test"
    assert second_button.callback_data == "channel_bonus:check"


def test_channel_bonus_keyboard_uses_fallback_callback_when_channel_url_missing() -> None:
    keyboard = build_channel_bonus_keyboard(channel_url=None)
    first_button = keyboard.inline_keyboard[0][0]

    assert first_button.callback_data == "channel_bonus:channel_unavailable"
