from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_limit_keyboard,
    build_friend_challenge_next_keyboard,
    build_friend_challenge_share_keyboard,
)


def test_friend_challenge_next_keyboard_contains_next_and_back() -> None:
    keyboard = build_friend_challenge_next_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001"
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "friend:next:00000000-0000-0000-0000-000000000001" in callbacks
    assert "home:open" in callbacks


def test_friend_challenge_back_keyboard_contains_home_only() -> None:
    keyboard = build_friend_challenge_back_keyboard()
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert callbacks == ["home:open"]


def test_friend_challenge_limit_keyboard_contains_buy_options_and_back() -> None:
    keyboard = build_friend_challenge_limit_keyboard()
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "buy:FRIEND_CHALLENGE_5" in callbacks
    assert "buy:PREMIUM_STARTER" in callbacks
    assert "home:open" in callbacks


def test_friend_challenge_share_keyboard_contains_share_url_and_back() -> None:
    keyboard = build_friend_challenge_share_keyboard(
        invite_link="https://t.me/quizarena_bot?start=fc_token",
        challenge_id="00000000-0000-0000-0000-000000000001",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.url and "https://t.me/share/url" in button.url for button in buttons)
    assert any(
        button.url and "https%3A%2F%2Ft.me%2Fquizarena_bot%3Fstart%3Dfc_token" in button.url
        for button in buttons
    )
    assert any(
        button.callback_data == "friend:next:00000000-0000-0000-0000-000000000001"
        for button in buttons
    )
    assert any(button.callback_data == "home:open" for button in buttons)


def test_friend_challenge_share_keyboard_without_link_contains_back_only() -> None:
    keyboard = build_friend_challenge_share_keyboard(
        invite_link=None,
        challenge_id=None,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert all(button.url is None for button in buttons)
    callbacks = [button.callback_data for button in buttons]
    assert callbacks == ["home:open"]
