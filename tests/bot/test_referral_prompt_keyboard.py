from app.bot.keyboards.referral_prompt import build_referral_prompt_keyboard


def test_referral_prompt_keyboard_contains_share_and_later_buttons() -> None:
    keyboard = build_referral_prompt_keyboard()
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert callbacks == ["referral:prompt:share", "referral:prompt:later"]
