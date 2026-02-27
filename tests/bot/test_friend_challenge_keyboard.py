from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_create_keyboard,
    build_friend_challenge_finished_keyboard,
    build_friend_challenge_limit_keyboard,
    build_friend_challenge_next_keyboard,
    build_friend_challenge_result_share_keyboard,
    build_friend_challenge_share_keyboard,
    build_friend_challenge_share_url,
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


def test_friend_challenge_create_keyboard_contains_type_options() -> None:
    keyboard = build_friend_challenge_create_keyboard()
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "friend:challenge:type:direct" in callbacks
    assert "friend:challenge:type:open" in callbacks
    assert "friend:challenge:type:tournament" in callbacks
    assert "home:open" in callbacks


def test_friend_challenge_finished_keyboard_contains_rematch_and_back() -> None:
    keyboard = build_friend_challenge_finished_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001"
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "friend:rematch:00000000-0000-0000-0000-000000000001" in callbacks
    assert "friend:series:best3:00000000-0000-0000-0000-000000000001" in callbacks
    assert "friend:share:result:00000000-0000-0000-0000-000000000001" in callbacks
    assert "home:open" in callbacks


def test_friend_challenge_finished_keyboard_can_hide_share() -> None:
    keyboard = build_friend_challenge_finished_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001",
        include_share=False,
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "friend:rematch:00000000-0000-0000-0000-000000000001" in callbacks
    assert "friend:series:best3:00000000-0000-0000-0000-000000000001" in callbacks
    assert "friend:share:result:00000000-0000-0000-0000-000000000001" not in callbacks
    assert "home:open" in callbacks


def test_friend_challenge_finished_keyboard_can_show_next_series_game() -> None:
    keyboard = build_friend_challenge_finished_keyboard(
        challenge_id="00000000-0000-0000-0000-000000000001",
        show_next_series_game=True,
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "friend:series:next:00000000-0000-0000-0000-000000000001" in callbacks


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
        total_rounds=5,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    share_buttons = [button for button in buttons if button.url]
    assert len(share_buttons) == 1
    assert "https://t.me/share/url" in (share_buttons[0].url or "")
    assert "https%3A%2F%2Ft.me%2Fquizarena_bot%3Fstart%3Dfc_token" in (share_buttons[0].url or "")
    assert "5+Fragen" in (share_buttons[0].url or "")
    assert any(
        button.callback_data == "friend:copy:00000000-0000-0000-0000-000000000001"
        for button in buttons
    )
    assert any(button.callback_data == "friend:my:duels" for button in buttons)
    assert any(button.callback_data == "home:open" for button in buttons)


def test_friend_challenge_share_keyboard_without_link_contains_back_only() -> None:
    keyboard = build_friend_challenge_share_keyboard(
        invite_link=None,
        challenge_id=None,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert all(button.url is None for button in buttons)
    callbacks = [button.callback_data for button in buttons]
    assert callbacks == ["friend:my:duels", "home:open"]


def test_friend_challenge_share_url_builder_encodes_target_and_text() -> None:
    url = build_friend_challenge_share_url(
        base_link="https://t.me/quizarena_bot",
        share_text="Proof Card",
    )
    assert "https://t.me/share/url" in url
    assert "https%3A%2F%2Ft.me%2Fquizarena_bot" in url
    assert "Proof+Card" in url


def test_friend_challenge_result_share_keyboard_contains_share_and_navigation() -> None:
    keyboard = build_friend_challenge_result_share_keyboard(
        share_url="https://t.me/share/url?url=https%3A%2F%2Ft.me%2Fquizarena_bot&text=proof",
        challenge_id="00000000-0000-0000-0000-000000000001",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.url and "https://t.me/share/url" in button.url for button in buttons)
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "friend:rematch:00000000-0000-0000-0000-000000000001" in callbacks
    assert "home:open" in callbacks
