from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.bot.handlers import promo, promo_input
from app.bot.texts.de import TEXTS_DE
from tests.bot.helpers import DummyCallback, DummyMessage


class _State:
    def __init__(self) -> None:
        self.set_states: list[object] = []
        self.data: dict[str, object] = {}

    async def set_state(self, state: object) -> None:
        self.set_states.append(state)

    async def update_data(self, data: dict[str, object]) -> dict[str, object]:
        self.data.update(data)
        return dict(self.data)

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)


def _valid_promo_open_state(
    state: _State,
    *,
    nonce: str = "nonce-1",
    message_id: int = 701,
) -> None:
    state.data[promo_input.PROMO_MENU_NONCE_KEY] = nonce
    state.data[promo_input.PROMO_MENU_MESSAGE_ID_KEY] = message_id


def _callback_message(*, message_id: int = 701, text: str = "Shop") -> DummyMessage:
    message = DummyMessage()
    message_any = cast(Any, message)
    message_any.message_id = message_id
    message_any.text = text
    message_any.chat = SimpleNamespace(id=99)
    return message


@pytest.mark.asyncio
async def test_handle_promo_open_prompts_for_accessible_callback_message(monkeypatch) -> None:
    monkeypatch.setattr(promo, "Message", DummyMessage)
    monkeypatch.setattr(promo, "is_user_in_quiz", _async_return(False))
    state = _State()
    _valid_promo_open_state(state)
    callback = DummyCallback(
        data="promo:open:nonce-1",
        from_user=SimpleNamespace(id=1),
        message=_callback_message(),
    )

    await promo.handle_promo_open(callback, state=state)  # type: ignore[arg-type]

    assert callback.message.answers[0].text == TEXTS_DE["msg.promo.input.hint"]
    assert callback.message.answers[0].kwargs["reply_markup"].inline_keyboard[0][
        0
    ].callback_data == ("promo:cancel")
    assert state.set_states == [promo.PromoCode.waiting_for_code]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_promo_open_ignores_inaccessible_callback_message() -> None:
    state = _State()
    callback = DummyCallback(
        data="promo:open",
        from_user=SimpleNamespace(id=1),
        message=DummyMessage(),
    )
    callback.message = cast(Any, object())

    await promo.handle_promo_open(callback, state=state)  # type: ignore[arg-type]

    assert state.set_states == []
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_promo_open_rejects_old_static_callback(monkeypatch) -> None:
    monkeypatch.setattr(promo, "Message", DummyMessage)
    state = _State()
    _valid_promo_open_state(state)
    callback = DummyCallback(
        data="promo:open",
        from_user=SimpleNamespace(id=1),
        message=_callback_message(),
    )

    await promo.handle_promo_open(callback, state=state)  # type: ignore[arg-type]

    assert callback.message.answers == []
    assert state.set_states == []
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_promo_open_rejects_wrong_source_message(monkeypatch) -> None:
    monkeypatch.setattr(promo, "Message", DummyMessage)
    state = _State()
    _valid_promo_open_state(state, message_id=701)
    callback = DummyCallback(
        data="promo:open:nonce-1",
        from_user=SimpleNamespace(id=1),
        message=_callback_message(message_id=702),
    )

    await promo.handle_promo_open(callback, state=state)  # type: ignore[arg-type]

    assert callback.message.answers == []
    assert state.set_states == []
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_promo_open_blocks_during_quiz(monkeypatch) -> None:
    monkeypatch.setattr(promo, "Message", DummyMessage)
    monkeypatch.setattr(promo, "is_user_in_quiz", _async_return(True))
    state = _State()
    _valid_promo_open_state(state)
    callback = DummyCallback(
        data="promo:open:nonce-1",
        from_user=SimpleNamespace(id=1),
        message=_callback_message(),
    )

    await promo.handle_promo_open(callback, state=state)  # type: ignore[arg-type]

    assert callback.message.answers == []
    assert state.set_states == []
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


def _async_return(value: object):
    async def _inner(*args, **kwargs):
        return value

    return _inner
