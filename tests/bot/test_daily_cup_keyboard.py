from app.bot.keyboards.daily_cup import (
    build_daily_cup_lobby_keyboard,
    build_daily_cup_share_keyboard,
    build_daily_cup_share_url,
)


def test_daily_cup_share_url_encodes_base_and_text() -> None:
    url = build_daily_cup_share_url(
        base_link="t.me/QuizArenaBot",
        share_text="🏆 Ich war dabei",
    )
    assert "https://t.me/share/url" in url
    assert "QuizArenaBot" in url
    assert "Ich+war+dabei" in url


def test_daily_cup_lobby_keyboard_uses_url_share_button_when_share_url_provided() -> None:
    keyboard = build_daily_cup_lobby_keyboard(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        can_join=False,
        play_challenge_id=None,
        show_share_result=True,
        share_url="https://t.me/share/url?url=t.me/QuizArenaBot&text=x",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.url and "https://t.me/share/url" in button.url for button in buttons)
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "daily:cup:share:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks


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


def test_daily_cup_share_keyboard_uses_callback_when_share_url_missing() -> None:
    keyboard = build_daily_cup_share_keyboard(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "daily:cup:share:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks


def test_daily_cup_share_keyboard_uses_url_when_provided() -> None:
    keyboard = build_daily_cup_share_keyboard(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        share_url="https://t.me/share/url?url=t.me%2FQuizArenaBot&text=x",
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    urls = [button.url for button in buttons if button.url]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert any(url and "https://t.me/share/url" in url for url in urls)
    assert "daily:cup:share:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks


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
