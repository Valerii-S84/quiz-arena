from app.bot.keyboards.daily_cup import (
    build_daily_cup_lobby_keyboard,
    build_daily_cup_share_keyboard,
    build_daily_cup_share_url,
)


def test_daily_cup_share_url_encodes_base_and_text() -> None:
    url = build_daily_cup_share_url(
        base_link="https://t.me/Deine_Deutsch_Quiz_bot",
        share_text="🏆 Ich war dabei",
    )
    assert "https://t.me/share/url" in url
    assert "Deine_Deutsch_Quiz_bot" in url
    assert "Ich+war+dabei" in url


def test_daily_cup_lobby_keyboard_uses_callback_share_button_when_enabled() -> None:
    keyboard = build_daily_cup_lobby_keyboard(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        can_join=False,
        play_challenge_id=None,
        show_share_result=True,
        share_url="https://t.me/share/url?url=https%3A%2F%2Ft.me%2FDeine_Deutsch_Quiz_bot&text=x",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "daily:cup:share:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert all(button.url is None for button in buttons)


def test_daily_cup_lobby_keyboard_uses_callback_share_when_share_url_missing() -> None:
    keyboard = build_daily_cup_lobby_keyboard(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        can_join=False,
        play_challenge_id=None,
        show_share_result=True,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    urls = [button.url for button in buttons if button.url]
    assert "daily:cup:share:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert not any(url and "https://t.me/share/url" in url for url in urls)


def test_daily_cup_share_keyboard_uses_inline_share_query() -> None:
    keyboard = build_daily_cup_share_keyboard(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    inline_queries = [
        button.switch_inline_query for button in buttons if button.switch_inline_query
    ]
    assert inline_queries == ["proof:daily:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]


def test_daily_cup_share_keyboard_ignores_text_share_url() -> None:
    keyboard = build_daily_cup_share_keyboard(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        share_url="https://t.me/share/url?url=https%3A%2F%2Ft.me%2FDeine_Deutsch_Quiz_bot&text=x",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    inline_queries = [
        button.switch_inline_query for button in buttons if button.switch_inline_query
    ]
    assert inline_queries == ["proof:daily:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]


def test_daily_cup_lobby_keyboard_shows_proof_card_button_when_enabled() -> None:
    keyboard = build_daily_cup_lobby_keyboard(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        can_join=False,
        play_challenge_id=None,
        show_share_result=False,
        show_proof_card=True,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "daily:cup:proof:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks


def test_daily_cup_lobby_keyboard_uses_custom_round_start_label() -> None:
    keyboard = build_daily_cup_lobby_keyboard(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        can_join=False,
        play_challenge_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        play_button_text="Runde starten",
        show_share_result=False,
    )

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    start_button = next(button for button in buttons if button.callback_data)
    assert start_button.text == "Runde starten"
    assert start_button.callback_data == "friend:next:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
