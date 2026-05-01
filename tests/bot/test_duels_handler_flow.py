from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.bot.handlers import gameplay_callbacks, gameplay_duels
from app.bot.texts.de import TEXTS_DE
from tests.bot.helpers import DummyCallback, DummyMessage


def _callback_payloads(reply_markup) -> list[str]:
    return [
        button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


class _RecordingRouter:
    def __init__(self) -> None:
        self.handlers: list[Callable[..., object]] = []

    def callback_query(
        self, _filter: object
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        def _decorator(handler: Callable[..., object]) -> Callable[..., object]:
            self.handlers.append(handler)
            return handler

        return _decorator


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


@pytest.mark.asyncio
async def test_arena_publish_friend_handler_delegates_to_flow(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_publish_flow(callback, **kwargs):
        captured["callback"] = callback
        captured.update(kwargs)

    monkeypatch.setattr(
        gameplay_duels.arena_duel_flow,
        "handle_arena_publish_friend",
        _fake_publish_flow,
    )
    callback = DummyCallback(
        data="arena:publish_friend:00000000-0000-0000-0000-000000000001",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await gameplay_duels.handle_arena_publish_friend(callback)

    assert captured["callback"] is callback
    assert captured["arena_publish_friend_re"] is gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE
    assert captured["parse_uuid_callback"] is gameplay_callbacks.parse_uuid_callback
    assert captured["publish_friend_challenge_to_arena"] is (
        gameplay_duels.publish_friend_challenge_to_arena
    )


def test_duels_register_includes_arena_publish_friend_callback() -> None:
    router = _RecordingRouter()

    gameplay_duels.register(cast(Any, router))

    assert gameplay_duels.handle_arena_publish_friend in router.handlers
