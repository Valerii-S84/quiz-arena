from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.handlers import gameplay_duels
from app.bot.texts.de import TEXTS_DE
from tests.bot.helpers import DummyCallback, DummyMessage


def _callback_payloads(reply_markup) -> list[str]:
    return [
        button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


@pytest.mark.asyncio
async def test_duels_menu_handler_shows_only_clean_mode_choices() -> None:
    callback = DummyCallback(
        data="duels:menu",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_duels.handle_duels_menu(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.duels.menu"]
    assert _callback_payloads(response.kwargs["reply_markup"]) == [
        "duels:arena",
        "duels:friend",
        "home:open",
    ]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_friend_duel_handler_uses_direct_seven_question_create_callback() -> None:
    callback = DummyCallback(
        data="duels:friend",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_duels.handle_friend_duel_open(callback)

    response = callback.message.answers[0]
    callbacks = _callback_payloads(response.kwargs["reply_markup"])
    assert response.text == TEXTS_DE["msg.duels.friend"]
    assert callbacks == ["friend:challenge:format:direct:7", "duels:menu"]
    assert "friend:challenge:create" not in callbacks
    assert "friend:challenge:type:direct" not in callbacks
    assert "friend:challenge:format:direct:5" not in callbacks
    assert "friend:challenge:format:direct:12" not in callbacks


@pytest.mark.asyncio
async def test_arena_create_handler_has_start_and_arena_back_only() -> None:
    callback = DummyCallback(
        data="arena:create",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_duels.handle_arena_create(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.duels.arena.create"]
    assert _callback_payloads(response.kwargs["reply_markup"]) == [
        "arena:start_create",
        "arena:list",
    ]
