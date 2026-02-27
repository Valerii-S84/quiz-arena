from app.bot.keyboards.tournament import (
    build_tournament_created_keyboard,
    build_tournament_format_keyboard,
    build_tournament_lobby_keyboard,
    build_tournament_share_keyboard,
    build_tournament_share_url,
)


def test_tournament_share_url_encodes_base_and_text() -> None:
    url = build_tournament_share_url(
        base_link="https://t.me/quiz_arena_bot?start=tournament_code",
        share_text="Turnier",
    )
    assert "https://t.me/share/url" in url
    assert "tournament_code" in url
    assert "Turnier" in url


def test_tournament_format_keyboard_contains_5_12_and_back() -> None:
    keyboard = build_tournament_format_keyboard()
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "friend:tournament:format:5" in callbacks
    assert "friend:tournament:format:12" in callbacks
    assert "friend:challenge:create" in callbacks


def test_tournament_created_keyboard_contains_share_copy_and_optional_start() -> None:
    keyboard = build_tournament_created_keyboard(
        invite_link="https://t.me/quiz_arena_bot?start=tournament_code",
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        can_start=True,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.url and "https://t.me/share/url" in button.url for button in buttons)
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "friend:tournament:copy:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert "friend:tournament:start:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert "friend:tournament:view:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks


def test_tournament_lobby_keyboard_contains_join_play_and_share_when_enabled() -> None:
    keyboard = build_tournament_lobby_keyboard(
        invite_code="abcdefabcdef",
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        can_join=True,
        can_start=True,
        play_challenge_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        show_share_result=True,
    )
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "friend:tournament:join:abcdefabcdef" in callbacks
    assert "friend:tournament:start:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert "friend:next:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" in callbacks
    assert "friend:tournament:share:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks


def test_tournament_share_keyboard_contains_url_and_refresh() -> None:
    keyboard = build_tournament_share_keyboard(
        share_url="https://t.me/share/url?url=x&text=y",
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.url and "https://t.me/share/url" in button.url for button in buttons)
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "friend:tournament:view:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert "home:open" in callbacks
