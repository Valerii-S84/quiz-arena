from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from tests.bot.helpers import DummyCallback


@pytest.mark.asyncio
async def test_handle_game_stop_with_missing_message_returns_error() -> None:
    callback = DummyCallback(data="game:stop", from_user=SimpleNamespace(id=1))
    callback.message = None

    await gameplay.handle_game_stop(callback)  # type: ignore[arg-type]

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_game_stop_sends_home_message_via_photo_helper(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def _fake_send_home_message(message, *, text: str) -> None:
        del message
        captured["text"] = text

    monkeypatch.setattr(gameplay, "_send_home_message", _fake_send_home_message)

    callback = DummyCallback(data="game:stop", from_user=SimpleNamespace(id=1))
    await gameplay.handle_game_stop(callback)

    assert captured["text"] == TEXTS_DE["msg.game.stopped"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_mode_with_missing_data_returns_error() -> None:
    callback = DummyCallback(data=None, from_user=SimpleNamespace(id=1))

    await gameplay.handle_mode(callback)  # type: ignore[arg-type]

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_answer_rejects_missing_callback_fields() -> None:
    callback = DummyCallback(data=None, from_user=None)

    await gameplay.handle_answer(callback)  # type: ignore[arg-type]

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]
