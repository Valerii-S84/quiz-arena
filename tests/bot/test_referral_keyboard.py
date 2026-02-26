from app.bot.keyboards.referral import build_referral_keyboard, build_referral_share_keyboard


def test_referral_keyboard_contains_share_reward_and_refresh_buttons() -> None:
    keyboard = build_referral_keyboard(
        invite_link="https://t.me/quiz_arena_bot?start=ref_ABC123",
        has_claimable_reward=True,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    callbacks = [button.callback_data for button in buttons]
    urls = [button.url for button in buttons]

    assert "referral:reward:MEGA_PACK_15" in callbacks
    assert "referral:reward:PREMIUM_STARTER" in callbacks
    assert "referral:open" in callbacks
    assert "referral:share" in callbacks
    assert all(url is None for url in urls)


def test_referral_keyboard_without_invite_link_skips_share_button() -> None:
    keyboard = build_referral_keyboard(
        invite_link=None,
        has_claimable_reward=False,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    callbacks = [button.callback_data for button in buttons]
    urls = [button.url for button in buttons]

    assert callbacks == ["referral:open"]
    assert all(url is None for url in urls)


def test_referral_share_keyboard_contains_share_url() -> None:
    keyboard = build_referral_share_keyboard(
        share_url="https://t.me/share/url?url=https%3A%2F%2Ft.me%2Fquiz_arena_bot",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    urls = [button.url for button in buttons if button.url]

    assert any(url and "https://t.me/share/url" in url for url in urls)
