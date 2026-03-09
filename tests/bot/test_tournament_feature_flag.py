from __future__ import annotations

from types import SimpleNamespace

from app.bot.keyboards import friend_challenge as friend_challenge_keyboard


def test_tournament_button_hidden_when_feature_flag_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        friend_challenge_keyboard,
        "get_settings",
        lambda: SimpleNamespace(tournament_friends_enabled=False),
    )

    keyboard = friend_challenge_keyboard.build_friend_challenge_create_keyboard()
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert "friend:challenge:type:tournament" not in callbacks


def test_tournament_button_visible_when_feature_flag_enabled(monkeypatch) -> None:
    monkeypatch.setattr(
        friend_challenge_keyboard,
        "get_settings",
        lambda: SimpleNamespace(tournament_friends_enabled=True),
    )

    keyboard = friend_challenge_keyboard.build_friend_challenge_create_keyboard()
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert "friend:challenge:type:tournament" in callbacks
