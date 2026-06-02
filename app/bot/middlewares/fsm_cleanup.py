from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject

_CLEAR_CALLBACKS = {"daily_challenge", "home:open", "menu:main", "play", "shop:open"}
_CLEAR_CALLBACK_PREFIXES = ("game:stop", "mode:")


def _should_clear_state(event: TelegramObject) -> bool:
    if isinstance(event, CallbackQuery):
        data = event.data or ""
        return data in _CLEAR_CALLBACKS or data.startswith(_CLEAR_CALLBACK_PREFIXES)
    if isinstance(event, Message):
        text = (event.text or "").strip()
        return text == "/start"
    return False


class FsmCleanupMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        state = data.get("state")
        if isinstance(state, FSMContext) and _should_clear_state(event):
            await state.clear()
        return await handler(event, data)
